import json
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from flask import url_for, current_app
from sqlalchemy import desc, asc, func
from MyLists import db
from MyLists.api.auth import current_user
from MyLists.utils.enums import Status, MediaType
from MyLists.utils.utils import safe_div, get_models_group


class MediaMixin:
    """ Media Mixin class for the SQLAlchemy classes: <Series>, <Anime>, <Movies>, <Games>, and <Books> """

    GROUP = None
    SIMILAR_GENRES = 12

    @property
    def actors_list(self) -> List:
        """ Fetch the media actors """
        return [d.name for d in self.actors]

    @property
    def genres_list(self) -> List:
        """ Fetch the media genres """
        return [d.genre for d in self.genres[:5]]

    @property
    def networks(self) -> List:
        """ Fetch the media networks """
        return [d.network for d in self.networks]

    @property
    def media_cover(self) -> str:
        """ Get the media cover """
        covers = f"{self.GROUP.value}_covers"
        return url_for("static", filename=f"covers/{covers}/{self.image_cover}")

    def get_similar_genres(self) -> List[Dict]:
        """ Get similar genre compared to the media in <media_details> """

        # Get media models
        media, _, media_genre, *_ = get_models_group(self.GROUP)

        # Check genre empty or unknown
        if len(self.genres_list) == 0 or self.genres_list[0] == "Unknown":
            return []

        sim_genres = (db.session.query(media, db.func.count(db.func.distinct(media_genre.genre)).label("genre_c"))
                      .join(media_genre, media.id == media_genre.media_id)
                      .filter(media_genre.genre.in_(self.genres_list), media_genre.media_id != self.id)
                      .group_by(media.id).having(db.func.count(db.func.distinct(media_genre.genre)) >= 1)
                      .order_by(desc("genre_c"))
                      .limit(self.SIMILAR_GENRES).all())

        return [{"media_id" : m[0].id, "media_name": m[0].name, "media_cover": m[0].media_cover} for m in sim_genres]

    def in_follows_lists(self) -> List[Dict]:
        """ Verify whether the <media> is included in the list of users followed by the <current_user> """

        # Fetch and set models
        _, media_list, *_ = get_models_group(self.GROUP)

        # Create query
        in_follows_lists = db.session.query(User, media_list, followers) \
            .join(User, User.id == followers.c.followed_id) \
            .join(media_list, media_list.user_id == followers.c.followed_id) \
            .filter(followers.c.follower_id == current_user.id, media_list.media_id == self.id).all()

        to_return = []
        for follow in in_follows_lists:
            to_return.append({
                "username": follow[0].username,
                "profile_image": follow[0].profile_image,
                "add_feeling": follow[0].add_feeling,
                **follow[1].to_dict(),
            })

        return to_return

    def get_user_list_info(self) -> bool | Dict:
        """ Retrieve if the <current_user> has the <media> in its <media_list> """

        media_in_user_list = self.list_info.filter_by(user_id=current_user.id).first()

        return media_in_user_list.to_dict() if media_in_user_list else False


class MediaListMixin:
    """ MediaListMixin SQLAlchemy model for: <SeriesList>, <AnimeList>, <MoviesList>, <GamesList>, and <BooksList> """

    def update_status(self, new_status: str) -> int:
        """ Change the status of the tv media (overwritten for other media) for the current user and return the
        new total """

        self.status = new_status
        new_total = self.total

        if new_status == Status.COMPLETED:
            self.current_season = len(self.media.eps_per_season)
            self.last_episode_watched = self.media.eps_per_season[-1].episodes
            self.total = self.media.total_episodes
            new_total = self.media.total_episodes
            self.completion_date = datetime.today()
        elif new_status in (Status.RANDOM, Status.PLAN_TO_WATCH):
            self.current_season = 1
            self.last_episode_watched = 0
            self.total = 0
            new_total = 0

        #  Reset rewatched value
        self.rewatched = 0

        return new_total

    @classmethod
    def get_media_count_per_status(cls, user_id: int) -> Dict:
        """ Get the media count for each allowed status and its total count """

        media_count = db.session.query(cls.status, func.count(cls.status)) \
            .filter_by(user_id=user_id).group_by(cls.status).all()

        # Create dict to store status count with default values
        status_count = {status.value: {"count": 0, "percent": 0} for status in cls.Status}

        # Calculate total media count
        total_media = sum(count for _, count in media_count)

        # Determine if no data available
        no_data = total_media == 0

        # Update <status_count> dict with actual values from <media_count> query
        if media_count:
            media_dict = {
                status.value: {"count": count, "percent": safe_div(count, total_media, True)}
                for status, count in media_count
            }
            status_count.update(media_dict)

        # Convert <status_count> dict to list of dict
        status_list = [{"status": key, **val} for key, val in status_count.items()]

        # Return formatted response
        return {"total_media": total_media, "no_data": no_data, "status_count": status_list}

    @classmethod
    def get_media_count_per_metric(cls, user: db.Model) -> List:
        """ Get the media count per metric (score or feeling) """

        # Determine metric (score or feeling) and corresponding range
        metric = cls.feeling if user.add_feeling else cls.score
        range_ = list(range(6)) if user.add_feeling else [i * 0.5 for i in range(21)]

        # Query database to get media count per metric for given <user_id>
        media_count = (db.session.query(metric, func.count(metric)).filter(cls.user_id == user.id, metric != None)
                       .group_by(metric).order_by(asc(metric)).all())

        # Create dict to store metric count with default values
        metric_counts = {str(val): 0 for val in range_}

        # Update <metric_counts> dict with actual values from <media_count> query
        new_metric = {str(val): count for val, count in media_count}
        metric_counts.update(new_metric)

        # Sort and return values as ordered list
        return list(OrderedDict(sorted(metric_counts.items())).values())

    @classmethod
    def get_media_metric(cls, user: db.Model) -> Dict:
        """ Get media mean score, percentage scored and qty of media scored """

        # Determine metric (feeling or score) based on user preferences
        metric = cls.feeling if user.add_feeling else cls.score

        # Query to calculate media metrics for given user_id
        media_metrics = db.session.query(func.count(metric), func.count(cls.media_id), func.sum(metric))\
            .filter(cls.user_id == user.id).all()

        # Calculate percentage scored and mean metric value
        count_metric, count_media, sum_metric = media_metrics[0]
        percent_metric = safe_div(count_metric, count_media, percentage=True)
        mean_metric = safe_div(sum_metric, count_metric)

        # Prepare and return result as dict
        return {"media_metric": count_metric, "percent_metric": percent_metric, "mean_metric": mean_metric}

    @classmethod
    def get_specific_total(cls, user_id: int) -> int:
        """ Retrieve a specific aggregate value: either the total count of episodes for TV shows, the total watched
        count along with the number of rewatched movies for movies, or the total number of pages read for books.
        This behavior is overridden by the <GamesList> class, which doesn't possess a replay feature or a distinct total
        attribute in its class table """

        # Query database to calculate specific total for given user_id
        specific_total = db.session.query(func.sum(cls.total)).filter(cls.user_id == user_id).scalar()

        if specific_total is None:
            specific_total = 0

        return specific_total

    @classmethod
    def get_favorites_media(cls, user_id: int, limit: int = 10) -> Dict:
        """ Get the user's favorites media """

        favorites_query = cls.query.filter_by(user_id=user_id, favorite=True).order_by(func.random()).all()

        favorites_list = [{
            "media_name": favorite.media.name,
            "media_id": favorite.media_id,
            "media_cover": favorite.media.media_cover
        } for favorite in favorites_query[:limit]]

        return {"favorites": favorites_list, "total_favorites": len(favorites_query)}

    @classmethod
    def get_available_sorting(cls, is_feeling: bool) -> Dict:
        """ Return the available sorting for movies, anime and series """

        release_date = "first_air_date"
        if cls.GROUP == MediaType.MOVIES:
            release_date = "release_date"

        # Get media
        media, *_ = get_models_group(cls.GROUP)

        sorting_dict = {
            "Title A-Z": media.name.asc(),
            "Title Z-A": media.name.desc(),
            "Release Date +": desc(getattr(media, release_date)),
            "Release Date -": asc(getattr(media, release_date)),
            "Score TMDB +": media.vote_average.desc(),
            "Score TMDB -": media.vote_average.asc(),
            "Comments": cls.comment.desc(),
            "Score +": cls.feeling.desc() if is_feeling else cls.score.desc(),
            "Score -": cls.feeling.asc() if is_feeling else cls.score.asc(),
        }

        return sorting_dict


class Badges(db.Model):
    """ Badges SQL model """

    GROUP = "Other"

    id = db.Column(db.Integer, primary_key=True)
    threshold = db.Column(db.Integer, nullable=False)
    image_id = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(100))
    genres_id = db.Column(db.String(100))

    @staticmethod
    def _read_badge_data_from_csv() -> List[List[str]]:
        """ Read badge data from CSV file and return it as list of lists """

        badges_file_path = Path(current_app.root_path, "static/csv_data/badges.csv")
        badge_data = []

        try:
            with open(badges_file_path, "r") as fp:
                lines = fp.readlines()
                lines.pop(0)
                badge_data = [line.strip().split(";") for line in lines]
        except Exception as e:
            current_app.logger.info(f"[ERROR] reading the badge data - {e}")

        return badge_data

    @classmethod
    def add_badges_to_db(cls):
        """ Add the badges to the db using the CSV in static/csv_data folder """

        badges_to_add = []
        for values in cls._read_badge_data_from_csv():
            if len(values) >= 5:
                threshold, image_id, title, badge_type, genres_id = values[:5]

                badges_to_add.append(cls(
                    threshold=int(threshold),
                    image_id=image_id,
                    title=title,
                    type=badge_type,
                    genres_id=genres_id if genres_id else None
                ))

        # Add all badges and commit changes
        db.session.add_all(badges_to_add)
        db.session.commit()

    @classmethod
    def refresh_db_badges(cls):
        """ Refresh the badges if new data are added in the CSV """

        # Read badge data from CSV file
        badge_data = cls._read_badge_data_from_csv()

        # Query existing badges from database
        badges = cls.query.order_by(cls.id).all()

        # Update existing badges with new data
        for i, badge in enumerate(badges):
            if i < len(badge_data):
                try:
                    genre_ids = badge_data[i][4] if badge_data[i][4] else None
                    threshold = int(badge_data[i][0])
                except ValueError:
                    print(f"Invalid data format for badge: {badge_data[i]}")
                    continue

                badge.threshold = threshold
                badge.image_id = badge_data[i][1]
                badge.title = badge_data[i][2]
                badge.type = badge_data[i][3]
                badge.genres_id = genre_ids

        # Commit changes to database
        db.session.commit()


class Ranks(db.Model):
    """ Ranks SQL model """

    GROUP = "Other"

    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.Integer, nullable=False)
    image_id = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    type = db.Column(db.String(50))

    @property
    def image(self) -> str:
        return url_for("static", filename=f"img/media_levels/{self.image_id}.png")

    @classmethod
    def add_ranks_to_db(cls):
        """ Add the ranks for the first time using CSV """

        list_all_ranks = []
        path = Path(current_app.root_path, "static/csv_data/media_levels.csv")
        with open(path) as fp:
            for line in fp:
                list_all_ranks.append(line.split(","))

        db.session.add_all([cls(level=int(r[0]), image_id=r[1], name=r[2]) for r in list_all_ranks[1:]])

    @classmethod
    def refresh_db_ranks(cls):
        """ Refresh the newly added ranks in the CSV to the db """

        list_all_ranks = []
        path = Path(current_app.root_path, "static/csv_data/media_levels.csv")
        with open(path) as fp:
            for line in fp:
                list_all_ranks.append(line.split(","))

        ranks = cls.query.order_by(cls.id).all()
        for i in range(1, len(list_all_ranks)):
            ranks[i-1].level = int(list_all_ranks[i][0])
            ranks[i-1].image_id = list_all_ranks[i][1]
            ranks[i-1].name = list_all_ranks[i][2]


class Frames(db.Model):
    """ Frames SQL model """

    GROUP = "Other"

    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.Integer, nullable=False)
    image_id = db.Column(db.String(50), nullable=False)

    @classmethod
    def add_frames_to_db(cls):
        """ Add the frames to the db using the CSV in static/csv_data folder """

        list_all_frames = []
        path = Path(current_app.root_path, "static/csv_data/profile_borders.csv")
        with open(path) as fp:
            for line in fp:
                list_all_frames.append(line.split(";"))

        for i in range(1, len(list_all_frames)):
            frame = cls(
                level=int(list_all_frames[i][0]),
                image_id=list_all_frames[i][1]
            )

            db.session.add(frame)

    @classmethod
    def refresh_db_frames(cls):
        """ Refresh the newly added frames in the CSV to the db """

        list_all_frames = []
        path = Path(current_app.root_path, "static/csv_data/profile_borders.csv")
        with open(path) as fp:
            for line in fp:
                list_all_frames.append(line.split(";"))

        # Query frames
        frames = cls.query.order_by(cls.id).all()

        for i in range(1, len(list_all_frames)):
            frames[i-1].level = int(list_all_frames[i][0])
            frames[i-1].image_id = list_all_frames[i][1]


class MyListsStats(db.Model):
    """ Model to get all global stats for MyLists """

    GROUP = "Stats"

    id = db.Column(db.Integer, primary_key=True)

    nb_users = db.Column(db.Integer)
    nb_media = db.Column(db.Text)
    total_time = db.Column(db.Text)

    top_media = db.Column(db.Text)
    top_genres = db.Column(db.Text)
    top_actors = db.Column(db.Text)
    top_authors = db.Column(db.Text)
    top_directors = db.Column(db.Text)
    top_developers = db.Column(db.Text)
    top_dropped = db.Column(db.Text)

    total_episodes = db.Column(db.Text)
    total_seasons = db.Column(db.Text)
    total_movies = db.Column(db.Text)
    total_pages = db.Column(db.Integer, default=0)

    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    @classmethod
    def get_all_stats(cls) -> Dict:
        """ Get all the stats from the SQL model """

        # Query stats
        all_stats = cls.query.order_by(cls.timestamp.desc()).first()

        # Dict with all data
        mylists_data = {}
        for key, value in all_stats.__dict__.items():
            if key not in ["id", "timestamp", "_sa_instance_state"]:
                if isinstance(value, str):
                    mylists_data[key] = json.loads(value)
                else:
                    mylists_data[key] = value

        return mylists_data


# Avoid circular imports
from MyLists.models.user_models import User, followers
