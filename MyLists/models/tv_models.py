from __future__ import annotations
import json
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Dict
from flask import current_app, abort
from sqlalchemy import func, text, extract, and_, not_
from sqlalchemy.sql.functions import count
from MyLists import db
from MyLists.api.auth import current_user
from MyLists.models.user_models import User, UserLastUpdate, Notifications
from MyLists.models.utils_models import MediaMixin, MediaListMixin
from MyLists.utils.enums import MediaType, Status, ExtendedEnum
from MyLists.utils.utils import change_air_format


class TVModel(db.Model):
    """ Abstract SQL model for the <Series> and <Anime> models """

    __abstract__ = True

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    original_name = db.Column(db.String(50), nullable=False)
    first_air_date = db.Column(db.String(30))
    last_air_date = db.Column(db.String(30))
    next_episode_to_air = db.Column(db.String(30))
    season_to_air = db.Column(db.Integer)
    episode_to_air = db.Column(db.Integer)
    homepage = db.Column(db.String(200))
    in_production = db.Column(db.Boolean)
    created_by = db.Column(db.String(100))
    duration = db.Column(db.Integer)
    total_seasons = db.Column(db.Integer, nullable=False)
    total_episodes = db.Column(db.Integer)
    origin_country = db.Column(db.String(20))
    status = db.Column(db.String(50))
    vote_average = db.Column(db.Float)
    vote_count = db.Column(db.Float)
    synopsis = db.Column(db.Text)
    popularity = db.Column(db.Float)
    image_cover = db.Column(db.String(100), nullable=False)
    api_id = db.Column(db.Integer, nullable=False)
    last_update = db.Column(db.DateTime, nullable=False)
    lock_status = db.Column(db.Boolean, default=0)

    """ --- Properties ------------------------------------------------------------ """
    @property
    def formated_date(self) -> List[str]:
        """ Format the first and last airing date """

        first_air_date = change_air_format(self.first_air_date, tv=True)
        last_air_date = change_air_format(self.last_air_date, tv=True)

        return [first_air_date, last_air_date]

    @property
    def eps_per_season_list(self) -> List:
        """ return the number of episode per season for the media """
        return [r.episodes for r in self.eps_per_season]

    @property
    def networks_list(self) -> List:
        """ return the number of episode per season for the media """
        return [r.network for r in self.networks]

    """ --- Methods --------------------------------------------------------------- """
    def to_dict(self, coming_next: bool = False):
        """ Serialization of series and anime """

        media_dict = {}
        if hasattr(self, "__table__"):
            media_dict = {c.name: getattr(self, c.name) for c in self.__table__.columns}

        if coming_next:
            media_dict["media_cover"] = self.media_cover
            media_dict["date"] = change_air_format(self.next_episode_to_air)
            return media_dict

        media_dict["media_cover"] = self.media_cover
        media_dict["formated_date"] = self.formated_date
        media_dict["actors"] = self.actors_list
        media_dict["genres"] = self.genres_list
        media_dict["similar_media"] = self.get_similar_genres()
        media_dict["eps_per_season"] = self.eps_per_season_list
        media_dict["networks"] = self.networks_list

        return media_dict

    def add_media_to_user(self, new_status: Enum, user_id: int) -> int:
        """ Add a new series or anime to the current user and return the <new_watched> value """

        new_watched, new_season, new_episode, completion_date = 1, 1, 1, None
        if new_status == Status.COMPLETED:
            new_season = len(self.eps_per_season)
            new_episode = self.eps_per_season[-1].episodes
            new_watched = self.total_episodes
            completion_date = datetime.today()
        elif new_status in (Status.RANDOM, Status.PLAN_TO_WATCH):
            new_episode = 0
            new_watched = 0

        # Get either <SeriesList> or <AnimeList> SQL model
        tv_list = eval(f"{self.__class__.__name__}List")

        # Set new media to user
        user_list = tv_list(
            user_id=user_id,
            media_id=self.id,
            current_season=new_season,
            last_episode_watched=new_episode,
            status=new_status,
            total=new_watched,
            completion_date=completion_date
        )

        db.session.add(user_list)

        return new_watched

    """ --- Class methods --------------------------------------------------------- """
    @classmethod
    def get_persons(cls, job: str, person: str) -> List[Dict]:
        """ Get either creator or actor and return its list of series/anime """

        if job == "creator":
            query = cls.query.filter(cls.created_by.ilike("%" + person + "%")).all()
        elif job == "actor":
            # Get <SeriesActors> or <AnimeActors> model
            tv_actors = eval(f"{cls.__name__}Actors")

            actors = tv_actors.query.filter(tv_actors.name == person).all()
            query = cls.query.filter(cls.id.in_([p.media_id for p in actors])).all()
        else:
            return abort(404)

        return [q.to_dict(coming_next=True) for q in query]

    """ --- Static methods -------------------------------------------------------- """
    @staticmethod
    def form_only() -> List[str]:
        """ Return the allowed fields for a form """
        return ["name", "original_name", "first_air_date", "last_air_date", "homepage", "created_by", "duration",
                "origin_country", "status", "synopsis"]


# --- SERIES ------------------------------------------------------------------------------------------------------


class Series(MediaMixin, TVModel):
    """ Series SQL model """

    GROUP = MediaType.SERIES
    TYPE = "Media"
    ORDER = 0

    genres = db.relationship("SeriesGenre", backref="series", lazy=True)
    actors = db.relationship("SeriesActors", backref="series", lazy=True)
    eps_per_season = db.relationship("SeriesEpisodesPerSeason", backref="series", lazy=False)
    networks = db.relationship("SeriesNetwork", backref="series", lazy=True)
    list_info = db.relationship("SeriesList", back_populates="media", lazy="dynamic")

    @classmethod
    def remove_series(cls):
        """ Remove all the series that are not present in a User list from the database and the disk """

        try:
            # noinspection PyComparisonWithNone
            series_to_delete = (cls.query.outerjoin(SeriesList, SeriesList.media_id == cls.id)
                                .filter(SeriesList.media_id == None).all())

            count_ = 0
            for series in series_to_delete:
                # Delete related records
                SeriesActors.query.filter_by(media_id=series.id).delete()
                SeriesGenre.query.filter_by(media_id=series.id).delete()
                SeriesNetwork.query.filter_by(media_id=series.id).delete()
                SeriesEpisodesPerSeason.query.filter_by(media_id=series.id).delete()
                UserLastUpdate.query.filter_by(media_type=MediaType.SERIES, media_id=series.id).delete()
                Notifications.query.filter_by(media_type="serieslist", media_id=series.id).delete()

                # Delete series
                Series.query.filter_by(id=series.id).delete()

                count_ += 1
                current_app.logger.info(f"Removed series with ID: [{series.id}]")

            current_app.logger.info(f"Total series removed: {count_}")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error occurred while removing series and related records: {str(e)}")
        finally:
            db.session.close()

    @classmethod
    def get_new_releasing_series(cls):
        """ Check for the new releasing series in a week or less from the TMDB API """

        try:
            # noinspection PyComparisonWithNone
            query = (db.session.query(cls.id, cls.episode_to_air, cls.season_to_air, cls.name, cls.next_episode_to_air,
                                      SeriesList.user_id)
            .join(SeriesList, cls.id == SeriesList.media_id)
            .filter(and_(
                cls.next_episode_to_air != None,
                cls.next_episode_to_air > datetime.utcnow(),
                cls.next_episode_to_air <= datetime.utcnow() + timedelta(days=7),
                not_(SeriesList.status.in_([Status.RANDOM, Status.DROPPED]))
            ))).all()

            for info in query:
                notif = Notifications.seek(info[5], "serieslist", info[0])

                if notif:
                    payload = json.loads(notif.payload_json)
                    if (int(payload["season"]) < int(info[2]) or
                            (int(payload["season"]) == int(info[2]) and int(payload["episode"]) < int(info[1]))):
                        pass
                    else:
                        continue

                release_date = datetime.strptime(info[4], "%Y-%m-%d").strftime("%b %d %Y")
                payload = {"name": info[3],
                           "release_date": release_date,
                           "season": f"{info[2]:02d}",
                           "episode": f"{info[1]:02d}"}

                # noinspection PyArgumentList
                new_notification = Notifications(
                    user_id=info[5],
                    media_type="serieslist",
                    media_id=info[0],
                    payload_json=json.dumps(payload)
                )
                db.session.add(new_notification)

            db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Error occurred while checking for new releasing series: {e}")
            db.session.rollback()


class SeriesList(MediaListMixin, db.Model):
    """ SeriesList SQL Model """

    GROUP = MediaType.SERIES
    TYPE = "List"
    DEFAULT_SORTING = "Title A-Z"
    DEFAULT_STATUS = Status.WATCHING
    DEFAULT_COLOR = "#216e7d"
    ORDER = 0

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    media_id = db.Column(db.Integer, db.ForeignKey('series.id'), nullable=False)
    current_season = db.Column(db.Integer, nullable=False)
    last_episode_watched = db.Column(db.Integer, nullable=False)
    status = db.Column(db.Enum(Status), nullable=False)
    rewatched = db.Column(db.Integer, nullable=False, default=0)
    favorite = db.Column(db.Boolean)
    feeling = db.Column(db.String(30))
    score = db.Column(db.Float)
    total = db.Column(db.Integer)
    comment = db.Column(db.Text)
    completion_date = db.Column(db.DateTime)

    # --- Relationships -----------------------------------------------------------
    media = db.relationship("Series", back_populates="list_info", lazy="joined")

    class Status(ExtendedEnum):
        """ Status class specific for the series and easiness """

        WATCHING = "Watching"
        COMPLETED = "Completed"
        ON_HOLD = "On Hold"
        RANDOM = "Random"
        DROPPED = "Dropped"
        PLAN_TO_WATCH = "Plan to Watch"

    """ --- Methods --------------------------------------------------------------- """
    def to_dict(self) -> Dict:
        """ Serialization of the serieslist class """

        media_dict = {}
        if hasattr(self, "__table__"):
            media_dict = {c.name: getattr(self, c.name) for c in self.__table__.columns}

        # Add more info
        media_dict["media_cover"] = self.media.media_cover
        media_dict["media_name"] = self.media.name
        media_dict["all_status"] = self.Status.to_list()
        media_dict["eps_per_season"] = self.media.eps_per_season_list

        return media_dict

    def update_total_watched(self, new_rewatch: int) -> int:
        """ Update the new total watched series and total and return new total """

        self.rewatched = new_rewatch

        # Calculate new total
        new_total = self.media.total_episodes + (new_rewatch * self.media.total_episodes)
        self.total = new_total

        return new_total

    def update_time_spent(self, old_value: int = 0, new_value: int = 0):
        """ Compute the new time spent for the user """

        old_time = current_user.time_spent_series
        current_user.time_spent_series = old_time + ((new_value - old_value) * self.media.duration)

    """ --- Class methods --------------------------------------------------------- """
    @classmethod
    def get_media_stats(cls, user: User) -> List[Dict]:
        """ Compute and return the series stats for the selected user """

        subquery = db.session.query(cls.media_id) \
            .filter(cls.user_id == user.id, cls.status != Status.PLAN_TO_WATCH).subquery()

        release_dates = (db.session.query((((extract("year", Series.first_air_date)) // 5) * 5).label("bin"),
                                         count(Series.first_air_date))
                         .join(subquery, (Series.id == subquery.c.media_id) & (Series.first_air_date != "Unknown"))
                         .group_by(text("bin")).order_by(Series.first_air_date.asc()).all())

        top_networks = (db.session.query(SeriesNetwork.network, func.count(SeriesNetwork.network).label("count"))
                        .join(subquery, (SeriesNetwork.media_id == subquery.c.media_id) & (SeriesNetwork.network != "Unknown"))
                        .group_by(SeriesNetwork.network).order_by(text("count desc")).limit(10).all())

        top_genres = (db.session.query(SeriesGenre.genre, func.count(SeriesGenre.genre).label("count"))
                      .join(subquery, (SeriesGenre.media_id == subquery.c.media_id) & (SeriesGenre.genre != "Unknown"))
                      .group_by(SeriesGenre.genre).order_by(text("count desc")).limit(10).all())

        top_actors = (db.session.query(SeriesActors.name, func.count(SeriesActors.name).label("count"))
                      .join(subquery, (SeriesActors.media_id == subquery.c.media_id) & (SeriesActors.name != "Unknown"))
                      .group_by(SeriesActors.name).order_by(text("count desc")).limit(10).all())

        top_countries = (db.session.query(Series.origin_country, func.count(Series.origin_country).label("count"))
                         .join(subquery, (Series.id == subquery.c.media_id) & (Series.origin_country != "Unknown"))
                         .group_by(Series.origin_country).order_by(text("count desc")).all())

        episodes = (db.session.query(((Series.total_episodes // 100 ) * 100).label("bin"), func.count(Series.id).label("count"))
                    .join(subquery, (Series.id == subquery.c.media_id) & (Series.total_episodes != 0))
                    .group_by("bin").order_by("bin").all())

        series_stats = [
            {"name": "Episodes", "values": [(f"{eps} - {eps + 99}", count_) for eps, count_ in episodes]},
            {"name": "Releases", "values": [(f"{year} - {year + 4}", count_) for year, count_ in release_dates]},
            {"name": "Actors", "values": [(actor, count_) for actor, count_ in top_actors]},
            {"name": "Genres", "values": [(genre, count_) for genre, count_ in top_genres]},
            {"name": "Networks", "values": [(network, count_) for network, count_ in top_networks]},
            {"name": "Countries", "values": [(country, count_) for country, count_ in top_countries]},
        ]

        return series_stats

    """ --- Static methods -------------------------------------------------------- """


class SeriesGenre(db.Model):
    """ Series genres SQL Model """

    GROUP = MediaType.SERIES

    id = db.Column(db.Integer, primary_key=True)
    media_id = db.Column(db.Integer, db.ForeignKey("series.id"), nullable=False)
    genre = db.Column(db.String(100), nullable=False)
    genre_id = db.Column(db.Integer, nullable=False)

    @staticmethod
    def get_available_genres() -> List:
        """ Return the available genres for the series """
        return ["All", "Action & Adventure", "Animation", "Comedy", "Crime", "Documentary", "Drama", "Family", "Kids",
                "Mystery", "News", "Reality", "Sci-Fi & Fantasy", "Soap", "Talk", "War & Politics", "Western"]


class SeriesEpisodesPerSeason(db.Model):
    """ Series episodes per season SQL Model """

    GROUP = MediaType.SERIES

    id = db.Column(db.Integer, primary_key=True)
    media_id = db.Column(db.Integer, db.ForeignKey("series.id"), nullable=False)
    season = db.Column(db.Integer, nullable=False)
    episodes = db.Column(db.Integer, nullable=False)


class SeriesNetwork(db.Model):
    """ Series networks SQL Model """

    GROUP = MediaType.SERIES

    id = db.Column(db.Integer, primary_key=True)
    media_id = db.Column(db.Integer, db.ForeignKey("series.id"), nullable=False)
    network = db.Column(db.String(150), nullable=False)


class SeriesActors(db.Model):
    """ Series actors SQL Model """

    GROUP = MediaType.SERIES

    id = db.Column(db.Integer, primary_key=True)
    media_id = db.Column(db.Integer, db.ForeignKey("series.id"), nullable=False)
    name = db.Column(db.String(150))


# --- ANIME -------------------------------------------------------------------------------------------------------


class Anime(MediaMixin, TVModel):
    """ Anime SQL Model """

    GROUP = MediaType.ANIME
    TYPE = "Media"
    ORDER = 1

    genres = db.relationship('AnimeGenre', backref='anime', lazy=True)
    actors = db.relationship('AnimeActors', backref='anime', lazy=True)
    eps_per_season = db.relationship('AnimeEpisodesPerSeason', backref='anime', lazy=False)
    networks = db.relationship('AnimeNetwork', backref='anime', lazy=True)
    list_info = db.relationship('AnimeList', back_populates='media', lazy='dynamic')

    @classmethod
    def remove_anime(cls):
        """ Remove all anime that are not present in a User list from the database and the disk """

        try:
            # Anime remover
            anime_to_delete = (cls.query.outerjoin(AnimeList, AnimeList.media_id == cls.id)
                               .filter(AnimeList.media_id.is_(None)).all())

            count_ = 0
            for anime in anime_to_delete:
                # Delete related records
                AnimeActors.query.filter_by(media_id=anime.id).delete()
                AnimeGenre.query.filter_by(media_id=anime.id).delete()
                AnimeNetwork.query.filter_by(media_id=anime.id).delete()
                AnimeEpisodesPerSeason.query.filter_by(media_id=anime.id).delete()
                UserLastUpdate.query.filter_by(media_type=MediaType.ANIME, media_id=anime.id).delete()
                Notifications.query.filter_by(media_type="animelist", media_id=anime.id).delete()

                # Delete Anime
                Anime.query.filter_by(id=anime.id).delete()

                count_ += 1
                current_app.logger.info(f"Removed anime with ID: [{anime.id}]")

            current_app.logger.info(f"Total anime removed: {count_}")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error occurred while removing anime and related records: {str(e)}")
        finally:
            db.session.close()

    @classmethod
    def get_new_releasing_anime(cls):
        """ Check for the new releasing anime in a week or less from the TMDB API """

        try:
            # noinspection PyComparisonWithNone
            query = (db.session.query(cls.id, cls.episode_to_air, cls.season_to_air, cls.name,
                                      cls.next_episode_to_air, AnimeList.user_id)
            .join(AnimeList, cls.id == AnimeList.media_id)
            .filter(and_(
                cls.next_episode_to_air != None,
                cls.next_episode_to_air > datetime.utcnow(),
                cls.next_episode_to_air <= datetime.utcnow() + timedelta(days=7),
                not_(AnimeList.status.in_(["RANDOM", "DROPPED"]))
            ))).all()

            for info in query:
                notif = Notifications.seek(info[5], "animelist", info[0])

                if notif:
                    payload = json.loads(notif.payload_json)
                    if (int(payload["season"]) < int(info[2]) or
                            (int(payload["season"]) == int(info[2])
                             and int(payload["episode"]) < int(info[1]))):
                        pass
                    else:
                        continue

                release_date = datetime.strptime(info[4], "%Y-%m-%d").strftime("%b %d %Y")
                payload = {"name": info[3],
                           "release_date": release_date,
                           "season": f"{info[2]:02d}",
                           "episode": f"{info[1]:02d}"}

                # noinspection PyArgumentList
                new_notification = Notifications(
                    user_id=info[5],
                    media_type="animelist",
                    media_id=info[0],
                    payload_json=json.dumps(payload)
                )
                db.session.add(new_notification)

            db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Error occurred while checking for new releasing anime: {e}")
            db.session.rollback()


class AnimeList(MediaListMixin, db.Model):
    """ Anime List SQL model """

    GROUP = MediaType.ANIME
    TYPE = "List"
    DEFAULT_SORTING = "Title A-Z"
    DEFAULT_STATUS = Status.WATCHING
    DEFAULT_COLOR = "#945141"
    ORDER = 1

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    media_id = db.Column(db.Integer, db.ForeignKey('anime.id'), nullable=False)
    current_season = db.Column(db.Integer, nullable=False)
    last_episode_watched = db.Column(db.Integer, nullable=False)
    status = db.Column(db.Enum(Status), nullable=False)
    rewatched = db.Column(db.Integer, nullable=False, default=0)
    favorite = db.Column(db.Boolean)
    feeling = db.Column(db.String(30))
    score = db.Column(db.Float)
    total = db.Column(db.Integer)
    comment = db.Column(db.Text)
    completion_date = db.Column(db.DateTime)

    # --- Relationships -------------------------------------------------------------
    media = db.relationship("Anime", back_populates='list_info', lazy=False)

    class Status(ExtendedEnum):
        """ New status class for easiness """

        WATCHING = "Watching"
        COMPLETED = "Completed"
        ON_HOLD = "On Hold"
        RANDOM = "Random"
        DROPPED = "Dropped"
        PLAN_TO_WATCH = "Plan to Watch"

    """ --- Methods --------------------------------------------------------------- """
    def to_dict(self) -> Dict:
        """ Serialization of the animelist class """

        media_dict = {}
        if hasattr(self, "__table__"):
            media_dict = {c.name: getattr(self, c.name) for c in self.__table__.columns}

        # Add more info
        media_dict["media_cover"] = self.media.media_cover
        media_dict["media_name"] = self.media.name
        media_dict["all_status"] = self.Status.to_list()
        media_dict["eps_per_season"] = self.media.eps_per_season_list

        return media_dict

    def update_total_watched(self, new_rewatch: int) -> int:
        """ Update the total anime watched for a user and return the new total """

        self.rewatched = new_rewatch

        # Calculate new total
        new_total = self.media.total_episodes + (new_rewatch * self.media.total_episodes)
        self.total = new_total

        return new_total

    def update_time_spent(self, old_value: int = 0, new_value: int = 0):
        """ Compute new anime time spent for the current user """

        old_time = current_user.time_spent_anime
        current_user.time_spent_anime = old_time + ((new_value - old_value) * self.media.duration)

    """ --- Class methods --------------------------------------------------------- """
    @classmethod
    def get_media_stats(cls, user: User) -> List[Dict]:
        """ Compute and return the anime stats for the selected user """

        subquery = db.session.query(cls.media_id) \
            .filter(cls.user_id == user.id, cls.status != Status.PLAN_TO_WATCH).subquery()

        release_dates = db.session.query((((extract("year", Anime.first_air_date))//10)*10).label("decade"),
                                         count(Anime.first_air_date)) \
            .join(subquery, (Anime.id == subquery.c.media_id) & (Anime.first_air_date != "Unknown")) \
            .group_by(text("decade")).order_by(Anime.first_air_date.asc()).all()

        top_networks = db.session.query(AnimeNetwork.network, func.count(AnimeNetwork.network).label("count")) \
            .join(subquery, (AnimeNetwork.media_id == subquery.c.media_id) & (AnimeNetwork.network != "Unknown")) \
            .group_by(AnimeNetwork.network).order_by(text("count desc")).limit(10).all()

        top_genres = db.session.query(AnimeGenre.genre, func.count(AnimeGenre.genre).label("count")) \
            .join(subquery, (AnimeGenre.media_id == subquery.c.media_id) & (AnimeGenre.genre != "Unknown")) \
            .group_by(AnimeGenre.genre).order_by(text("count desc")).limit(10).all()

        top_actors = db.session.query(AnimeActors.name, func.count(AnimeActors.name).label("count")) \
            .join(subquery, (AnimeActors.media_id == subquery.c.media_id) & (AnimeActors.name != "Unknown")) \
            .group_by(AnimeActors.name).order_by(text("count desc")).limit(10).all()

        episodes = db.session.query(((Anime.total_episodes // 50 ) * 50).label("bin"),
                                    func.count(Anime.id).label("count")) \
            .join(subquery, (Anime.id == subquery.c.media_id) & (Anime.total_episodes != 0)) \
            .group_by("bin").order_by("bin").all()

        series_stats = [
            {"name": "Episodes", "values": [(eps, count_) for eps, count_ in episodes]},
            {"name": "Releases", "values": [(release, count_) for release, count_ in release_dates]},
            {"name": "Actors", "values": [(actor, count_) for actor, count_ in top_actors]},
            {"name": "Genres", "values": [(genre, count_) for genre, count_ in top_genres]},
            {"name": "Networks", "values": [(network, count_) for network, count_ in top_networks]},
        ]

        return series_stats


class AnimeGenre(db.Model):
    """ Anime genre SQL model """

    GROUP = MediaType.ANIME

    id = db.Column(db.Integer, primary_key=True)
    media_id = db.Column(db.Integer, db.ForeignKey("anime.id"), nullable=False)
    genre = db.Column(db.String(100), nullable=False)
    genre_id = db.Column(db.Integer, nullable=False)

    @staticmethod
    def get_available_genres() -> List:
        """ Return the available genres for the anime """
        return ["All", "Action", "Adventure", "Cars", "Comedy", "Dementia", "Demons", "Mystery", "Drama",
                "Ecchi", "Fantasy", "Game", "Hentai", "Historical", "Horror", "Magic", "Martial Arts", "Mecha",
                "Music", "Samurai", "Romance", "School", "Sci-Fi", "Shoujo", "Shonen", "Space", "Sports",
                "Super Power", "Vampire", "Harem", "Slice Of Life", "Supernatural", "Military", "Police",
                "Psychological", "Thriller", "Seinen", "Josei"]


class AnimeEpisodesPerSeason(db.Model):
    """ Anime episode per season SQL model """

    GROUP = MediaType.ANIME

    id = db.Column(db.Integer, primary_key=True)
    media_id = db.Column(db.Integer, db.ForeignKey('anime.id'), nullable=False)
    season = db.Column(db.Integer, nullable=False)
    episodes = db.Column(db.Integer, nullable=False)


class AnimeNetwork(db.Model):
    """ Anime network SQL model """

    GROUP = MediaType.ANIME

    id = db.Column(db.Integer, primary_key=True)
    media_id = db.Column(db.Integer, db.ForeignKey('anime.id'), nullable=False)
    network = db.Column(db.String(150), nullable=False)


class AnimeActors(db.Model):
    """ Anime actors SQL model """

    GROUP = MediaType.ANIME

    id = db.Column(db.Integer, primary_key=True)
    media_id = db.Column(db.Integer, db.ForeignKey("anime.id"), nullable=False)
    name = db.Column(db.String(150))

