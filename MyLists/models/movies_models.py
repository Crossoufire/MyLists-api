from __future__ import annotations
import json
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Dict
from flask import current_app, abort
from sqlalchemy import func, text, and_
from MyLists import db
from MyLists.api.auth import current_user
from MyLists.models.user_models import User, UserLastUpdate, Notifications
from MyLists.models.utils_models import MediaMixin, MediaListMixin
from MyLists.utils.enums import MediaType, Status, ExtendedEnum
from MyLists.utils.utils import change_air_format


class Movies(MediaMixin, db.Model):
    """ Movies SQLAlchemy model """

    GROUP = MediaType.MOVIES
    TYPE = "Media"
    ORDER = 2

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    original_name = db.Column(db.String(50), nullable=False)
    director_name = db.Column(db.String(100))
    release_date = db.Column(db.String(30))
    homepage = db.Column(db.String(200))
    released = db.Column(db.String(30))
    duration = db.Column(db.Integer)
    original_language = db.Column(db.String(20))
    synopsis = db.Column(db.Text)
    vote_average = db.Column(db.Float)
    vote_count = db.Column(db.Float)
    popularity = db.Column(db.Float)
    budget = db.Column(db.Float)
    revenue = db.Column(db.Float)
    tagline = db.Column(db.String(30))
    image_cover = db.Column(db.String(100), nullable=False)
    api_id = db.Column(db.Integer, nullable=False)
    lock_status = db.Column(db.Boolean, default=0)

    genres = db.relationship("MoviesGenre", backref="movies", lazy=True)
    actors = db.relationship("MoviesActors", backref="movies", lazy=True)
    list_info = db.relationship("MoviesList", back_populates="media", lazy="dynamic")

    """ --- Methods --------------------------------------------------------------- """
    def to_dict(self, coming_next: bool = False) -> Dict:
        """ Serialization of the movies class """

        media_dict = {}
        if hasattr(self, "__table__"):
            media_dict = {c.name: getattr(self, c.name) for c in self.__table__.columns}

        if coming_next:
            media_dict["media_cover"] = self.media_cover
            media_dict["date"] = change_air_format(self.release_date)
            return media_dict

        media_dict["media_cover"] = self.media_cover
        media_dict["formated_date"] = change_air_format(self.release_date)
        media_dict["actors"] = self.actors_list
        media_dict["genres"] = self.genres_list
        media_dict["similar_media"] = self.get_similar_genres()

        return media_dict

    def add_media_to_user(self, new_status: Enum, user_id: int) -> int:
        """ Add a new movie to the user and return the <new_watched> value """

        new_watched = 1 if new_status != Status.PLAN_TO_WATCH else 0

        # noinspection PyArgumentList
        add_movie = MoviesList(
            user_id=user_id,
            media_id=self.id,
            status=new_status,
            total=new_watched
        )
        db.session.add(add_movie)

        return new_watched

    """ --- Class methods --------------------------------------------------------- """
    @classmethod
    def get_persons(cls, job: str, person: str) -> List[Dict]:
        """ Get the movies from a specific creator or actor """

        if job == "creator":
            query = cls.query.filter(cls.director_name.ilike(f"%{person}%")).all()
        elif job == "actor":
            actors = MoviesActors.query.filter(MoviesActors.name == person).all()
            query = cls.query.filter(cls.id.in_([p.media_id for p in actors])).all()
        else:
            return abort(404)

        return [q.to_dict(coming_next=True) for q in query]

    @classmethod
    def remove_movies(cls):
        """ Remove all movies that are not present in a User list from the database and the disk """

        try:
            # Movies remover
            movies_to_delete = (cls.query.outerjoin(MoviesList, MoviesList.media_id == cls.id)
                                .filter(MoviesList.media_id.is_(None)).all())
            count = 0
            for movie in movies_to_delete:
                # Delete related records
                MoviesActors.query.filter_by(media_id=movie.id).delete()
                MoviesGenre.query.filter_by(media_id=movie.id).delete()
                UserLastUpdate.query.filter_by(media_type=MediaType.MOVIES, media_id=movie.id).delete()
                Notifications.query.filter_by(media_type="movieslist", media_id=movie.id).delete()

                # Delete movie
                Movies.query.filter_by(id=movie.id).delete()

                count += 1
                current_app.logger.info(f"Removed movie with ID: [{movie.id}]")

            current_app.logger.info(f"Total movies removed: {count}")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error occurred while removing movies and related records: {str(e)}")
        finally:
            db.session.close()

    @classmethod
    def get_new_releasing_movies(cls):
        """ Check for the new releasing movies in a week or less from the TMDB API """

        try:
            query = (db.session.query(cls.id, MoviesList.user_id, cls.release_date, cls.name)
            .join(MoviesList, cls.id == MoviesList.media_id)
            .filter(and_(
                cls.release_date != None,
                cls.release_date > datetime.utcnow(),
                cls.release_date <= datetime.utcnow() + timedelta(days=7),
                MoviesList.status != Status.PLAN_TO_WATCH,
                ))).all()

            for info in query:
                notif = Notifications.seek(info[1], "movieslist", info[0])

                if notif is None:
                    release_date = datetime.strptime(info[2], "%Y-%m-%d").strftime("%b %d %Y")
                    payload = {"name": info[3].name,
                               "release_date": release_date}

                    # noinspection PyArgumentList
                    new_notification = Notifications(
                        user_id=info[1],
                        media_type="movieslist",
                        media_id=info[0],
                        payload_json=json.dumps(payload)
                    )
                    db.session.add(new_notification)

            db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Error occurred while checking for new releasing anime: {e}")
            db.session.rollback()

    """ --- Static methods -------------------------------------------------------- """
    @staticmethod
    def form_only() -> List[str]:
        """ Return the allowed fields for a form """
        return ["name", "original_name", "director_name", "release_date", "homepage", "original_language",
                "duration", "synopsis", "budget", "revenue", "tagline"]


class MoviesList(MediaListMixin, db.Model):
    """ Movieslist SQL model """

    GROUP = MediaType.MOVIES
    TYPE = "List"
    DEFAULT_SORTING = "Title A-Z"
    DEFAULT_STATUS = Status.COMPLETED
    DEFAULT_COLOR = "#8c7821"
    ORDER = 2

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    media_id = db.Column(db.Integer, db.ForeignKey("movies.id"), nullable=False)
    status = db.Column(db.Enum(Status), nullable=False)
    rewatched = db.Column(db.Integer, nullable=False, default=0)
    total = db.Column(db.Integer)
    favorite = db.Column(db.Boolean)
    feeling = db.Column(db.String(50))
    score = db.Column(db.Float)
    comment = db.Column(db.Text)
    completion_date = db.Column(db.DateTime)

    # --- Relationships -----------------------------------------------------------
    media = db.relationship("Movies", back_populates="list_info", lazy=False)

    class Status(ExtendedEnum):
        """ Special status class for the movies """

        COMPLETED = "Completed"
        PLAN_TO_WATCH = "Plan to Watch"

    """ --- Methods ---------------------------------------------------------------- """
    def to_dict(self) -> Dict:
        """ Serialization of the movieslist class """

        media_dict = {}
        if hasattr(self, "__table__"):
            media_dict = {c.name: getattr(self, c.name) for c in self.__table__.columns}

        # Add more info
        media_dict["media_cover"] = self.media.media_cover
        media_dict["media_name"] = self.media.name
        media_dict["all_status"] = self.Status.to_list()

        return media_dict

    def update_total_watched(self, new_rewatch: int) -> int:
        """ Update the new total watched movies and total and return new total """

        self.rewatched = new_rewatch

        # Calculate new total
        new_total = 1 + new_rewatch
        self.total = new_total

        return new_total

    def update_status(self, new_status: Enum) -> int:
        """ Change the movie status for the current user and return the new total watched """

        # Set new status
        self.status = new_status

        if new_status == Status.COMPLETED:
            self.completion_date = datetime.today()
            self.total = 1
            new_total = 1
        else:
            self.total = 0
            new_total = 0

        # Reset rewatched value
        self.rewatched = 0

        return new_total

    def update_time_spent(self, old_value: int = 0, new_value: int = 0):
        """ Return new computed time for the movies """

        old_time = current_user.time_spent_movies
        current_user.time_spent_movies = old_time + ((new_value - old_value) * self.media.duration)

    """ --- Class methods --------------------------------------------------------- """
    @classmethod
    def get_media_stats(cls, user: User) -> List[Dict]:
        """ Get the movies stats for a user and return a list of dict """

        subquery = (db.session.query(cls.media_id).filter(cls.user_id == user.id, cls.status != Status.PLAN_TO_WATCH)
                    .subquery())

        release_dates = (db.session.query((((func.extract("year", Movies.release_date)) // 10) * 10).label("decade"),
                                          func.count(Movies.release_date))
                         .join(subquery, (Movies.id == subquery.c.media_id) & (Movies.release_date != "Unknown"))
                         .group_by("decade").order_by(Movies.release_date.asc()).all())

        top_directors = (db.session.query(Movies.director_name, func.count(Movies.director_name).label("count"))
                         .join(subquery, (Movies.id == subquery.c.media_id) & (Movies.director_name != "Unknown"))
                         .group_by(Movies.director_name).order_by(text("count desc")).limit(10).all())

        top_languages = (db.session.query(Movies.original_language, func.count(Movies.original_language).label("nb"))
                         .join(subquery, (Movies.id == subquery.c.media_id) & (Movies.original_language != "Unknown"))
                         .group_by(Movies.original_language).order_by(text("nb desc")).limit(5).all())

        runtimes = (db.session.query(((Movies.duration//30)*30).label("bin"), func.count(Movies.id).label("count"))
                    .join(subquery, (Movies.id == subquery.c.media_id) & (Movies.duration != "Unknown"))
                    .group_by("bin").order_by("bin").all())

        top_actors = (db.session.query(MoviesActors.name, func.count(MoviesActors.name).label("count"))
                      .join(subquery, (MoviesActors.media_id == subquery.c.media_id) & (MoviesActors.name != "Unknown"))
                      .group_by(MoviesActors.name).order_by(text("count desc")).limit(10).all())

        top_genres = (db.session.query(MoviesGenre.genre, func.count(MoviesGenre.genre).label("count"))
                      .join(subquery, (MoviesGenre.media_id == subquery.c.media_id) & (MoviesGenre.genre != "Unknown"))
                      .group_by(MoviesGenre.genre).order_by(text("count desc")).limit(10).all())

        movies_stats = [
            {"name": "Runtimes", "values": [(run, count_) for run, count_ in runtimes]},
            {"name": "Releases", "values": [(rel, count_) for rel, count_ in release_dates]},
            {"name": "Actors", "values": [(actor, count_) for actor, count_ in top_actors]},
            {"name": "Directors", "values": [(director, count_) for director, count_ in top_directors]},
            {"name": "Genres", "values": [(genre,count_) for genre, count_ in top_genres]},
            {"name": "Languages", "values": [(lang, count_) for lang, count_ in top_languages]},
        ]

        return movies_stats


class MoviesGenre(db.Model):
    """ Movies genres SQL model """

    GROUP = MediaType.MOVIES

    id = db.Column(db.Integer, primary_key=True)
    media_id = db.Column(db.Integer, db.ForeignKey("movies.id"), nullable=False)
    genre = db.Column(db.String(100), nullable=False)
    genre_id = db.Column(db.Integer, nullable=False)

    @staticmethod
    def get_available_genres() -> List:
        """ Return the available genres for the movies """
        return ["All", "Action", "Adventure", "Animation", "Comedy", "Crime", "Documentary", "Drama", "Family",
                "Fantasy", "History", "Horror", "Music", "Mystery", "Romance", "Science Fiction", "TV Movie",
                "Thriller", "War", "Western"]


class MoviesActors(db.Model):
    """ Movies actors SQL model """

    GROUP = MediaType.MOVIES

    id = db.Column(db.Integer, primary_key=True)
    media_id = db.Column(db.Integer, db.ForeignKey("movies.id"), nullable=False)
    name = db.Column(db.String(150))


# class MoviesSim(db.Model):
#     """ Movies similarities SQL model """
#
#     GROUP = MediaType.MOVIES
#
#     id = db.Column(db.Integer, primary_key=True)
#     media_id = db.Column(db.Integer, db.ForeignKey("movies.id"), nullable=False)
#     media_id_2 = db.Column(db.Integer, db.ForeignKey("movies.id"), nullable=False)
#     similarity = db.Column(db.Integer)
#
#     @classmethod
#     def compute_all_similarities(cls):
#         from sklearn.feature_extraction.text import TfidfVectorizer
#         from sklearn.metrics.pairwise import cosine_similarity
#         from sklearn.preprocessing import OneHotEncoder
#         from sklearn.compose import ColumnTransformer
#         import pandas as pd
#         import numpy as np
#
#         # Movies with genres
#         movies_query  = (db.session.query(Movies.id.label("movie_id"), Movies.name, Movies.synopsis,
#                                           func.group_concat(MoviesGenre.genre).label("genres"))
#                          .join(MoviesGenre, MoviesGenre.media_id == Movies.id).group_by(Movies.id))
#
#         # Transform to Dataframe
#         df = pd.read_sql(movies_query.statement, db.engine)
#
#         # TfidfVectorizer with common parameters for English text
#         tfidf_vectorizer = TfidfVectorizer(
#             stop_words="english",
#             ngram_range=(1, 2),
#             max_df=0.85,
#             sublinear_tf=True,
#             smooth_idf=True,
#         )
#
#         # One-Hot-Encoder and TF-IDF vectorization
#         preprocessor = ColumnTransformer(
#             transformers=[
#                 ("genres", OneHotEncoder(), ["genres"]),
#                 ("synopsis", tfidf_vectorizer, "synopsis"),
#             ],
#         )
#
#         # Combine genres encoding and TF-IDF vectorization
#         concatenated_matrix = preprocessor.fit_transform(df)
#
#         # Compute cosine similarity
#         cosine_sim = cosine_similarity(concatenated_matrix, concatenated_matrix)
#
#         # Specific movie ID
#         query_movie_id = 6560
#
#         # Find row index corresponding to given movie ID
#         movie_index = df[df["movie_id"] == query_movie_id].index[0]
#
#         # Get cosine similarities for specified movie
#         movie_cosine_similarities = cosine_sim[movie_index]
#
#         # Find indices of top 12 most similar movies (excluding itself)
#         most_similar_movie_indices = np.argsort(movie_cosine_similarities)[::-1][1:13]
#
#         # Get movie name and cosine similarities of top 12 most similar movies
#         top_12_movie_names = df.iloc[most_similar_movie_indices]["name"].tolist()
#         top_12_cosine_similarities = movie_cosine_similarities[most_similar_movie_indices]
#
#         # Print top 12 results
#         for i, (name, similarity) in enumerate(zip(top_12_movie_names, top_12_cosine_similarities), 1):
#             print(f"{i:02d}. {name} -- Cosine similarity = {similarity:.3f}")
