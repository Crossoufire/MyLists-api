from __future__ import annotations
import secrets
from datetime import datetime, timedelta
from enum import Enum
from time import time
from typing import List, Dict
import jwt
import pytz
from flask import url_for, current_app, abort
from flask_bcrypt import check_password_hash
from sqlalchemy import desc, func, Integer, case, select, asc, or_
from sqlalchemy.ext.hybrid import hybrid_property
from MyLists import db
from MyLists.api.auth import current_user
from MyLists.utils.enums import RoleType, MediaType, Status
from MyLists.utils.utils import get_level, get_models_group, change_air_format, get_models_type, safe_div


followers = db.Table(
    "followers",
    db.Column("follower_id", db.Integer, db.ForeignKey("user.id")),
    db.Column("followed_id", db.Integer, db.ForeignKey("user.id"))
)


class Token(db.Model):
    """ Class for the management of the user's connexion tokens """

    GROUP = "User"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    access_token = db.Column(db.String(64), nullable=False, index=True)
    access_expiration = db.Column(db.DateTime, nullable=False)
    refresh_token = db.Column(db.String(64), nullable=False, index=True)
    refresh_expiration = db.Column(db.DateTime, nullable=False)

    # --- Relationships ------------------------------------------------------------
    user = db.relationship("User", back_populates="token")

    def generate(self):
        """ Generate the <access token> and the <refresh token> for a user """

        self.access_token = secrets.token_urlsafe()
        self.access_expiration = datetime.utcnow() + timedelta(minutes=current_app.config["ACCESS_TOKEN_MINUTES"])
        self.refresh_token = secrets.token_urlsafe()
        self.refresh_expiration = datetime.utcnow() + timedelta(days=current_app.config["REFRESH_TOKEN_DAYS"])

    def expire(self, delay: int = None):
        """ Add an expiration time on both the <access token> and the <refresh token> """

        # Add 5 second delay for simultaneous requests
        if delay is None:
            delay = 5 if not current_app.testing else 0

        self.access_expiration = datetime.utcnow() + timedelta(seconds=delay)
        self.refresh_expiration = datetime.utcnow() + timedelta(seconds=delay)

    @classmethod
    def clean(cls):
        """ Remove all tokens that have been expired for more than a day to keep the database clean """

        yesterday = datetime.utcnow() - timedelta(days=1)
        cls.query.filter(cls.refresh_expiration < yesterday).delete()

        # Commit changes
        db.session.commit()


class User(db.Model):
    """ User class representation """

    GROUP = "User"

    def __repr__(self):
        return f"<{self.username} - {self.id}>"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(15), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    registered_on = db.Column(db.DateTime, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    image_file = db.Column(db.String(20), nullable=False, default="default.jpg")
    background_image = db.Column(db.String(50), nullable=False, default="default.jpg")
    private = db.Column(db.Boolean, nullable=False, default=False)
    role = db.Column(db.Enum(RoleType), nullable=False, default=RoleType.USER)
    biography = db.Column(db.Text)
    transition_email = db.Column(db.String(120))
    activated_on = db.Column(db.DateTime)
    last_notif_read_time = db.Column(db.DateTime)
    active = db.Column(db.Boolean, nullable=False, default=False)

    time_spent_series = db.Column(db.Integer, nullable=False, default=0)
    time_spent_anime = db.Column(db.Integer, nullable=False, default=0)
    time_spent_movies = db.Column(db.Integer, nullable=False, default=0)
    time_spent_games = db.Column(db.Integer, nullable=False, default=0)
    time_spent_books = db.Column(db.Integer, nullable=False, default=0)

    profile_views = db.Column(db.Integer, nullable=False, default=0)
    series_views = db.Column(db.Integer, nullable=False, default=0)
    anime_views = db.Column(db.Integer, nullable=False, default=0)
    movies_views = db.Column(db.Integer, nullable=False, default=0)
    games_views = db.Column(db.Integer, nullable=False, default=0)
    books_views = db.Column(db.Integer, nullable=False, default=0)

    add_anime = db.Column(db.Boolean, nullable=False, default=False)
    add_books = db.Column(db.Boolean, nullable=False, default=False)
    add_games = db.Column(db.Boolean, nullable=False, default=False)
    add_feeling = db.Column(db.Boolean, nullable=False, default=False)

    last_seen = db.Column(db.DateTime, default=datetime.utcnow)

    # --- Relationships ----------------------------------------------------------------
    token = db.relationship("Token", back_populates="user", lazy="noload")
    series_list = db.relationship("SeriesList", backref="user", lazy="select")
    anime_list = db.relationship("AnimeList", backref="user", lazy="select")
    movies_list = db.relationship("MoviesList", backref="user", lazy="select")
    games_list = db.relationship("GamesList", backref="user", lazy="select")
    last_updates = db.relationship("UserLastUpdate", backref="user", order_by="desc(UserLastUpdate.date)", lazy="dynamic")
    followed = db.relationship("User", secondary=followers, primaryjoin=(followers.c.follower_id == id),
                               secondaryjoin=(followers.c.followed_id == id), order_by="asc(User.username)",
                               backref=db.backref("followers", lazy="dynamic"), lazy="dynamic")

    @property
    def profile_image(self) -> str:
        """ Return the profile image url """
        return url_for("static", filename=f"profile_pics/{self.image_file}")

    @property
    def back_image(self) -> str:
        """ Return the background image url """
        return url_for("static", filename=f"background_pics/{self.background_image}")

    @property
    def profile_border(self) -> str:
        """ Get the border of the profile based on the profile level """

        base_path = "img/profile_borders"
        profile_border = "border_40.png"

        profile_border_level = f"{(self.profile_level // 8) + 1:02d}"
        if profile_border_level < "40":
            profile_border = f"border_{profile_border_level}.png"

        return url_for("static", filename=f"{base_path}/{profile_border}")

    @property
    def followers_count(self):
        """ Return the number of followers of the user """
        return self.followers.count()

    @hybrid_property
    def profile_level(self) -> int:
        """ Return the user's profile level """

        # Calculate <total_time>
        total_time = self.time_spent_series + self.time_spent_movies

        if self.add_anime: total_time += self.time_spent_anime
        if self.add_books: total_time += self.time_spent_books
        if self.add_games: total_time += self.time_spent_games

        return int(get_level(total_time))

    # noinspection PyMethodParameters
    @profile_level.expression
    def profile_level(cls) -> int:
        """ Return the user's profile level as an SQLAlchemy query for the <Hall of Fame> route """

        # Calculate <total_time>
        total_time = cls.time_spent_series + cls.time_spent_movies
        total_time = case(*[(cls.add_anime, total_time + cls.time_spent_anime)], else_=total_time)
        total_time = case(*[(cls.add_books, total_time + cls.time_spent_books)], else_=total_time)
        total_time = case(*[(cls.add_games, total_time + cls.time_spent_games)], else_=total_time)

        profile_level = func.cast(((func.power(400 + 80 * total_time, 0.5)) - 20) / 40, Integer)

        return profile_level

    def to_dict(self) -> Dict:
        """ Serialize the user class - does not include <email> and <password> """

        excluded_attrs = ["email", "password"]
        user_dict = {c.name: getattr(self, c.name) for c in self.__table__.columns if c.name not in excluded_attrs}

        # Additional attributes
        user_dict.update({
            "role": self.role.value,
            "registered_on": self.registered_on.strftime("%d %b %Y"),
            "profile_image": self.profile_image,
            "back_image": self.back_image,
            "profile_level": self.profile_level,
            "profile_border": self.profile_border,
            "followers_count": self.followers_count,
        })

        return user_dict

    def verify_password(self, password: str) -> bool:
        """ Verify the user password hash using bcrypt """
        return check_password_hash(self.password, password)

    def ping(self):
        """ Ping the user """
        self.last_seen = datetime.utcnow()

    def revoke_all_tokens(self):
        """ Revoke all the <access token> and <refresh token> of the current user """

        Token.query.filter(Token.user == self).delete()

        # Commit changes
        db.session.commit()

    def generate_auth_token(self) -> Token:
        """ Generate and return an authentication token for the user """

        token = Token(user=self)
        token.generate()

        return token

    def check_autorization(self, username: str) -> User:
        """ Check if the user can see the other <user> profile page """

        user = self.query.filter_by(username=username).first()
        if not user:
            return abort(404)

        # <admin> protection
        if user.username == "admin" and self.role != RoleType.ADMIN:
            return abort(403)

        return user

    def set_view_count(self, user: User, media_type: Enum):
        """ Set new view count to the <user> if different from <current_user> """

        if self.role != RoleType.ADMIN and self.id != user.id:
            setattr(user, f"{media_type.value}_views", getattr(user, f"{media_type.value}_views") + 1)

    def add_follow(self, user: User):
        """ Add the followed user to the current user """

        if not self.is_following(user):
            self.followed.append(user)

    def is_following(self, user: User) -> bool:
        """ Check if the current user is not already following the other user """
        return self.followed.filter(followers.c.followed_id == user.id).count() > 0

    def remove_follow(self, user: User):
        """ Remove the followed user from the current user """

        if self.is_following(user):
            self.followed.remove(user)

    def get_last_notifications(self, limit_: int = 8) -> List[Notifications]:
        """ Get the last <limit_> notifications for the current user """

        notif = (Notifications.query.filter_by(user_id=self.id)
                 .order_by(desc(Notifications.timestamp)).limit(limit_).all())

        return notif

    def count_notifications(self) -> int:
        """ Count the number of unread notifications for the current user """
        last_notif_time = self.last_notif_read_time or datetime(1900, 1, 1)
        return Notifications.query.filter_by(user_id=self.id).filter(Notifications.timestamp > last_notif_time).count()

    def get_global_media_stats(self) -> Dict:
        """ Get the media list global stats """

        # Fetch and select <list> models
        list_models = get_models_type("List")
        list_models = [ml for ml in list_models if getattr(self, f"add_{ml.GROUP.value.lower()}", None) is None
                       or getattr(self, f"add_{ml.GROUP.value.lower()}")]

        # Calculate time per media (in hours)
        to_query = [getattr(User, f"time_spent_{ml.GROUP.value}") for ml in list_models]
        time_per_media = [t / 60 for t in db.session.query(*to_query).filter_by(id=self.id).first()]

        # Total time (in hours)
        total_hours = sum(time_per_media)

        # Combine queries for total media, percent scored, and mean score
        count_per_feeling = []
        if self.add_feeling:
            subqueries = [(db.session.query(ml.feeling, func.count(ml.feeling))
                           .filter(ml.user_id == self.id, ml.feeling != None).group_by(ml.feeling)
                           .order_by(asc(ml.feeling))) for ml in list_models]

            results = [db.session.execute(sub).all() for sub in subqueries]

            results_dict = {key: 0 for key in range(0, 6)}
            for sublist in results:
                for tuple_pair in sublist:
                    key, value = tuple_pair
                    results_dict[key] += value
            count_per_feeling = list(reversed(list(results_dict.values())))

        metric = "feeling" if self.add_feeling else "score"
        subqueries = [(db.session.query(func.count(ml.media_id), func.count(getattr(ml, metric)),
                                        func.coalesce(func.sum(getattr(ml, metric)), 0))
                       .filter(ml.user_id == self.id)) for ml in list_models]
        query = subqueries[0].union_all(*subqueries[1:])
        results = db.session.execute(query).all()

        # Calculation for total media, percent scored, and mean score
        total_media, total_scored, sum_score = map(sum, zip(*results))
        percent_scored = safe_div(total_scored, total_media, percentage=True)
        mean_score = safe_div(sum_score, total_scored)

        data = dict(
            total_hours=int(total_hours),
            total_days=round(total_hours / 24, 0),
            total_media=total_media,
            time_per_media=time_per_media,
            color_per_media=[ml.DEFAULT_COLOR for ml in list_models],
            total_scored=total_scored,
            percent_scored=percent_scored,
            mean_score=mean_score,
            count_per_feeling=count_per_feeling,
        )

        return data

    def get_one_media_details(self, media_type: MediaType) -> Dict:
        """ Get one media details for the selected user """

        _, media_list, *_ = get_models_group(media_type)

        media_dict = dict(
            media_type=media_type.value,
            specific_total=media_list.get_specific_total(self.id),
            count_per_metric=media_list.get_media_count_per_metric(self),
            # stats=media_list.get_media_stats(self),
            time_hours=int(getattr(self, f"time_spent_{media_type.value}") / 60),
            time_days=int(getattr(self, f"time_spent_{media_type.value}") / 1440),
        )

        media_dict.update(media_list.get_media_count_per_status(self.id))
        media_dict.update(media_list.get_favorites_media(self.id, limit=10))
        media_dict.update(media_list.get_media_metric(self))

        return media_dict

    def get_list_levels(self) -> List[Dict]:
        """ Get all list levels for a user """

        list_models = [ml for ml in get_models_type("List") if getattr(self, f"add_{ml.GROUP.value.lower()}", None)
                       is None or getattr(self, f"add_{ml.GROUP.value.lower()}")]

        # Fetch all ranks at once
        from MyLists.models.utils_models import Ranks
        all_ranks = {rank.level: {"image": rank.image, "name": rank.name} for rank in Ranks.query.all()}

        level_per_ml = []
        for i, ml in enumerate(list_models):
            time_in_min = getattr(self, f"time_spent_{ml.GROUP.value}")

            # Get level and percent
            level, level_percent = map(float, divmod(get_level(time_in_min), 1))
            level_percent = level_percent * 100

            # Fetch associated rank from dict
            rank_info = all_ranks.get(min(level, 149))

            level_per_ml.append({
                "media_type": ml.GROUP.value,
                "level": level,
                "level_percent": level_percent,
                "rank_image": rank_info["image"],
                "rank_name": rank_info["name"],
            })

        return level_per_ml

    def get_last_updates(self, limit_: int) -> List[Dict]:
        """ Get the last media updates of the current user """
        last_updates = self.last_updates.filter_by(user_id=self.id).limit(limit_).all()
        return [update.to_dict() for update in last_updates]

    def get_follows_updates(self, limit_: int) -> List[Dict]:
        """ Get the last updates of the current user's followed users """

        follows_updates = (UserLastUpdate.query
                           .filter(UserLastUpdate.user_id.in_([u.id for u in self.followed.all()]))
                           .order_by(desc(UserLastUpdate.date)).limit(limit_))

        return [{ "username": update.user.username, **update.to_dict()} for update in follows_updates]

    def generate_jwt_token(self, expires_in: int = 600) -> str:
        """ Generate a <register token> or a <forgot password token> """

        token = jwt.encode(
            payload={"token": self.id, "exp": time() + expires_in},
            key=current_app.config["SECRET_KEY"],
            algorithm="HS256",
        )

        return token

    @classmethod
    def create_search_results(cls, search: str, page: int = 1) -> Dict:
        """ Create the <users> search results """

        users = (cls.query.filter(cls.username.like(f"%{search}%"), cls.role != RoleType.ADMIN)
                 .paginate(page=page, per_page=8, error_out=True))

        users_list = [{
            "name": user.username,
            "image_cover": user.profile_image,
            "date": user.registered_on.strftime("%d %b %Y"),
            "media_type": "User",
            } for user in users.items]

        return {"items": users_list, "total": users.total, "pages": users.pages}

    @classmethod
    def get_total_time_spent(cls) -> Dict:
        """ Get the total time spent [minutes] by all the users for all the media and return a dict """

        query = (db.session.query(func.sum(cls.time_spent_series), func.sum(cls.time_spent_anime),
                                  func.sum(cls.time_spent_movies), func.sum(cls.time_spent_books),
                                  func.sum(cls.time_spent_games))
                 .filter(cls.role != RoleType.ADMIN, cls.active == True).first())

        total_time_spent = [0 if not v else v for v in query]

        results = {
            "total": sum(total_time_spent),
            "series": total_time_spent[0] // 60,
            "anime": total_time_spent[1] // 60,
            "movies": total_time_spent[2] // 60,
            "books": total_time_spent[3] // 60,
            "games": total_time_spent[4] // 60,
        }

        return results

    @staticmethod
    def verify_access_token(access_token: str) -> User:
        """ Verify the <access token> viability of the user and return the user object or None """

        token = db.session.scalar(select(Token).where(Token.access_token == access_token))

        if token:
            if token.access_expiration > datetime.utcnow():
                token.user.ping()
                db.session.commit()

                return token.user

    @staticmethod
    def verify_refresh_token(refresh_token: str, access_token: str) -> Token:
        """ Verify the <refresh token> of the user """

        token = Token.query.filter_by(refresh_token=refresh_token, access_token=access_token).first()
        if token:
            if token.refresh_expiration > datetime.utcnow():
                return token

            # Try to refresh with expired token: revoke all tokens from user as precaution
            token.user.revoke_all_tokens()

            # Commit changes
            db.session.commit()

    @staticmethod
    def verify_jwt_token(token: str) -> User | None:
        """ Verify the user <jwt token> for the validation of his account or for the forgot password """

        try:
            user_id = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])["token"]
        except:
            return None

        return User.query.filter_by(id=user_id).first()


class UserLastUpdate(db.Model):
    """ UserLastUpdate SQL model """

    GROUP = "User"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    media_name = db.Column(db.String(50), nullable=False)
    media_type = db.Column(db.Enum(MediaType), nullable=False)
    media_id = db.Column(db.Integer)

    old_status = db.Column(db.Enum(Status))
    new_status = db.Column(db.Enum(Status))
    old_season = db.Column(db.Integer)
    new_season = db.Column(db.Integer)
    old_episode = db.Column(db.Integer)
    new_episode = db.Column(db.Integer)
    old_playtime = db.Column(db.Integer)
    new_playtime = db.Column(db.Integer)
    old_page = db.Column(db.Integer)
    new_page = db.Column(db.Integer)

    date = db.Column(db.DateTime, index=True, nullable=False)

    def to_dict(self) -> Dict:
        """ Transform a <UserLastUpdate> object into a dict """

        update_dict = {}

        # Page update
        if self.old_page is not None and self.new_page is not None and self.old_page >= 0 and self.new_page >= 0:
            update_dict["update"] = [f"p. {int(self.old_page)}", f"p. {int(self.new_page)}"]

        # Playtime update
        if self.old_playtime is not None and self.new_playtime is not None and self.old_playtime >= 0 and self.new_playtime >= 0:
            update_dict["update"] = [f"{int(self.old_playtime / 60)} h", f"{int(self.new_playtime / 60)} h"]

        # Season or episode update
        if not self.old_status and not self.new_status:
            update_dict["update"] = [
                f"S{self.old_season:02d}.E{self.old_episode:02d}",
                f"S{self.new_season:02d}.E{self.new_episode:02d}",
            ]

        # Status update
        elif self.old_status and self.new_status:
            update_dict["update"] = [f"{self.old_status.value}", f"{self.new_status.value}"]

        # Newly added media
        elif not self.old_status and self.new_status:
            update_dict["update"] = ["{}".format(self.new_status.value)]

        # Update date and add media name
        update_dict["date"] = self.date.replace(tzinfo=pytz.UTC).isoformat()
        update_dict["media_name"] = self.media_name
        update_dict["media_id"] = self.media_id
        update_dict["media_type"] = self.media_type.value

        return update_dict

    @classmethod
    def set_last_update(cls, media, media_type, old_status=None, new_status=None, old_season=None, new_season=None,
                        old_episode=None, new_episode=None, old_playtime=None, new_playtime=None, old_page=None,
                        new_page=None):
        """ Set the last updates depending on *lots* of parameters """

        # Check query
        previous_entry = (cls.query.filter_by(user_id=current_user.id, media_type=media_type, media_id=media.id)
                          .order_by(desc(cls.date)).first())

        time_difference  = 10000
        if previous_entry:
            time_difference  = (datetime.utcnow() - previous_entry.date).total_seconds()

        # Add new last updates
        update = cls(
            user_id=current_user.id,
            media_name=media.name,
            media_id=media.id,
            media_type=media_type,
            old_status=old_status,
            new_status=new_status,
            old_season=old_season,
            new_season=new_season,
            old_episode=old_episode,
            new_episode=new_episode,
            old_playtime=old_playtime,
            new_playtime=new_playtime,
            old_page=old_page,
            new_page=new_page,
            date=datetime.utcnow()
        )

        if time_difference > 600:
            db.session.add(update)
        else:
            db.session.delete(previous_entry)
            db.session.add(update)

    @classmethod
    def get_history(cls, media_type: MediaType, media_id: int) -> List[Dict]:
        """ Get the <current_user> history for a specific <media> """

        history = cls.query.filter(cls.user_id == current_user.id, cls.media_type == media_type,
                                   cls.media_id == media_id).order_by(desc(UserLastUpdate.date)).all()

        return [update.to_dict() for update in history]


class Notifications(db.Model):
    """ Notification SQL model """

    GROUP = "User"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    media_type = db.Column(db.String(50))
    media_id = db.Column(db.Integer)
    payload_json = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)

    @classmethod
    def seek(cls, user_id: int, media_type: str, media_id: int):
        """ Seek if a notification exists for a user concerning a <media_type> and a <media_id> """

        data = (cls.query.filter_by(user_id=user_id, media_type=media_type, media_id=media_id)
                .order_by(desc(cls.timestamp)).first())

        return data


def get_coming_next(media_type: MediaType) -> List[Dict]:
    """ Fetch the media that are 'coming next' for the current user """

    # Get models
    media, media_list, *_ = get_models_group(media_type)

    # Get date attribute
    if media_type in (MediaType.SERIES, MediaType.ANIME):
        media_date = "next_episode_to_air"
    else:
        media_date = "release_date"

    if media_type == MediaType.GAMES:
        subquery = (media.query
                    .join(media_list, media.id == media_list.media_id)
                    .filter(media_list.user_id == current_user.id, media_list.status != Status.DROPPED)
                    .order_by(getattr(media, media_date).asc())
                    .all())

        data = []
        for game in subquery:
            try:
                if datetime.utcfromtimestamp(int(game.release_date)) > datetime.utcnow():
                    serialized = game.to_dict()
                    serialized["date"] = change_air_format(game.release_date, games=True)
                    data.append(serialized)
            except:
                if game.release_date == "Unknown":
                    serialized = game.to_dict()
                    serialized["date"] = "Unknown"
                    data.append(serialized)

        return data

    query = (db.session.query(media)
             .join(media_list, media.id == media_list.media_id)
             .filter(getattr(media, media_date) > datetime.utcnow())
             .filter(media_list.user_id == current_user.id)
             .filter(media_list.status.notin_([Status.DROPPED, Status.RANDOM]))
             .order_by(getattr(media, media_date).asc())
             .all())

    return [q.to_dict(coming_next=True) for q in query]


# def get_all_media_info(user: User) -> Tuple[List, Dict]:
#     """ Get all the media data and the global stats for a user "/profile" route """
#
#     # Fetch all "list" models
#     list_models = get_models_type("List")
#
#     # Remove media not used by <user>
#     if not user.add_anime:
#         list_models.remove(AnimeList)
#     if not user.add_books:
#         list_models.remove(BooksList)
#     if not user.add_games:
#         list_models.remove(GamesList)
#
#     # Fetch all data for each media in <media_type>
#     media_data, to_divide  = [], len(list_models)
#
#     for model in list_models:
#         media_dict = dict(
#             media_type=model.GROUP.value,
#             media_name=model.GROUP.value.capitalize(),
#             specific_total=model.get_specific_total(user.id),
#             media_color=model.DEFAULT_COLOR,
#             count_per_metric=model.get_media_count_per_metric(user),
#         )
#         media_dict.update(get_media_level_and_time(user, model.GROUP.value))
#         media_dict.update(model.get_media_count_per_status(user.id))
#         media_dict.update(model.get_favorites_media(user.id, limit=10))
#         media_dict.update(model.get_media_metric(user))
#         media_dict["time_hours"] = round(media_dict["time_min"]/60)
#         media_dict["time_days"] = round(media_dict["time_min"]/1440, 2)
#
#         if media_dict["time_min"] == 0:
#             to_divide -= 1
#
#         media_data.append(media_dict)
#
#     # Get global media data from each <media_dict>
#     media_global = dict(
#         total_hours=sum([x["time_hours"] for x in media_data]),
#         total_media=sum([x["total_media"] for x in media_data]),
#         chart_data=[x["time_hours"] for x in media_data],
#         chart_colors=[x["media_color"] for x in media_data],
#         total_media_scored=sum([x["media_metric"] for x in media_data]),
#         total_mean_score=safe_div(sum([x["mean_metric"] for x in media_data]), to_divide),
#         list_all_metric=[sum(val) for val in zip(*[media["count_per_metric"] for media in media_data])]
#     )
#
#     return media_data, media_global
