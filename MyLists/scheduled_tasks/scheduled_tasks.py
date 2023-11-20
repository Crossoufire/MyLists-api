from __future__ import annotations
import json
import logging
import os
from datetime import datetime, timedelta
import dotenv
import requests
from flask import current_app
from sqlalchemy import func
from MyLists import db
from MyLists.classes.Global_stats import GlobalStats
from MyLists.models.books_models import BooksList, Books
from MyLists.models.games_models import GamesList, Games
from MyLists.models.movies_models import MoviesList, Movies
from MyLists.models.tv_models import SeriesList, AnimeList, Anime, Series
from MyLists.models.user_models import User
from MyLists.models.utils_models import MyListsStats
from MyLists.scheduled_tasks.media_refresher import automatic_media_refresh
from MyLists.scheduled_tasks.remove_old_covers import (_remove_old_series_covers, _remove_old_anime_covers,
                                                       _remove_old_movies_covers, _remove_old_books_covers,
                                                       _remove_old_games_covers)
from MyLists.utils.utils import get_models_type


def remove_non_list_media():
    """ Remove all media that are not present in a User list from the database and the disk """

    current_app.logger.info("###############################################################################")
    current_app.logger.info("[SYSTEM] - Starting automatic media remover -")

    Series.remove_series()
    Anime.remove_anime()
    Movies.remove_movies()
    Games.remove_games()
    Books.remove_books()

    # Commit changes
    db.session.commit()

    current_app.logger.info("[SYSTEM] - Finished Automatic media remover -")
    current_app.logger.info("###############################################################################")


def remove_all_old_covers():
    """ Remove all the old covers on disk if they are not present in the database """

    current_app.logger.info("###############################################################################")
    current_app.logger.info("[SYSTEM] - Starting automatic covers remover -")

    _remove_old_series_covers()
    _remove_old_anime_covers()
    _remove_old_movies_covers()
    _remove_old_books_covers()
    _remove_old_games_covers()

    current_app.logger.info("[SYSTEM] - Finished automatic covers remover")
    current_app.logger.info('###############################################################################')


def add_new_releasing_media():
    """ Remove all the old covers on disk if they are not present in the database """

    current_app.logger.info("###############################################################################")
    current_app.logger.info("[SYSTEM] - Starting checking new releasing media -")

    Series.get_new_releasing_series()
    Anime.get_new_releasing_anime()
    Movies.get_new_releasing_movies()
    Games.get_new_releasing_games()

    current_app.logger.info("[SYSTEM] - Finished checking new releasing media -")
    current_app.logger.info("###############################################################################")


def automatic_movies_locking():
    """ Automatically lock the movies that are more than about 6 months old """

    current_app.logger.info("###############################################################################")
    current_app.logger.info("[SYSTEM] - Starting automatic movies locking -")

    all_movies = Movies.query.filter(Movies.lock_status != True).all()
    count_locked = 0
    count_not_locked = 0

    now_date = (datetime.utcnow() - timedelta(days=180))
    for movie in all_movies:
        try:
            release_date = datetime.strptime(movie.release_date, "%Y-%m-%d")
            if release_date < now_date and movie.image_cover != "default.jpg":
                movie.lock_status = True
                count_locked += 1
            else:
                movie.lock_status = False
                count_not_locked += 1
        except:
            movie.lock_status = False
            count_not_locked += 1

    db.session.commit()

    current_app.logger.info(f"Number of movies locked: {count_locked}")
    current_app.logger.info(f"Number of movies not locked: {count_not_locked}")
    current_app.logger.info("[SYSTEM] - Finished automatic movies locking -")
    current_app.logger.info("###############################################################################")


def update_IGDB_API():
    """ Refresh the IGDB API token """

    current_app.logger.info("###############################################################################")
    current_app.logger.info("[SYSTEM] - Starting fetching new IGDB API key -")

    try:
        r = requests.post(f"https://id.twitch.tv/oauth2/token?client_id={current_app.config['CLIENT_IGDB']}&"
                          f"client_secret={current_app.config['SECRET_IGDB']}&grant_type=client_credentials")
        response = json.loads(r.text)

        # Fetch new IGDB API KEY/TOKEN
        new_IGDB_token = response["access_token"]

        # Get <.env> file and load it
        dotenv_file = dotenv.find_dotenv()
        dotenv.load_dotenv(dotenv_file)

        # Set new IGDB API KEY to environment
        os.environ["IGDB_API_KEY"] = f"{new_IGDB_token}"

        # Set new IGDB API KEY to app config
        current_app.config["IGDB_API_KEY"] = f"{new_IGDB_token}"

        # Write new IGDB API KEY to <.env> file
        dotenv.set_key(dotenv_file, "IGDB_API_KEY", f"{new_IGDB_token}")
    except Exception as e:
        current_app.logger.error(f"[ERROR] - While updating the IGDB API key: {e}")

    current_app.logger.info("[SYSTEM] - Finished fetching new IGDB API key")
    current_app.logger.info("###############################################################################")


def compute_media_time_spent():
    """ Compute the total time watched/played/read for each media for each user """

    current_app.logger.info("###############################################################################")
    current_app.logger.info("[SYSTEM] - Starting to compute the total time spent for each user -")

    all_media = get_models_type("Media")
    all_media_list = get_models_type("List")

    for media, media_list in zip(all_media, all_media_list):
        if media_list in (SeriesList, AnimeList, MoviesList):
            query = (db.session.query(User, media.duration, media_list.total, func.sum(media.duration * media_list.total))
                     .join(media, media.id == media_list.media_id)
                     .join(User, User.id == media_list.user_id)
                     .group_by(media_list.user_id).all())
        elif media_list == GamesList:
            query = (db.session.query(User, media_list.playtime, media_list.score, func.sum(media_list.playtime))
                     .join(media, media.id == media_list.media_id)
                     .join(User, User.id == media_list.user_id)
                     .group_by(media_list.user_id).all())
        elif media_list == BooksList:
            query = (db.session.query(User, media_list.total, media_list.score,
                                     func.sum(BooksList.TIME_PER_PAGE * media_list.total))
                     .join(media, media.id == media_list.media_id)
                     .join(User, User.id == media_list.user_id)
                     .group_by(media_list.user_id).all())
        else:
            return

        for q in query:
            setattr(q[0], f"time_spent_{media.GROUP.value}", q[3])

    # Commit changes
    db.session.commit()

    current_app.logger.info("[SYSTEM] - Finished computing the total time spent for each user -")
    current_app.logger.info("###############################################################################")


def update_Mylists_stats():
    """ Update the MyLists global stats """

    # Get global stats
    stats = GlobalStats()

    total_time = User.get_total_time_spent()
    media_top = stats.get_top_media()
    media_genres = stats.get_top_genres()
    media_actors = stats.get_top_actors()
    media_authors = stats.get_top_authors()
    media_developers = stats.get_top_developers()
    media_directors = stats.get_top_directors()
    media_dropped = stats.get_top_dropped()
    media_eps_seas = stats.get_total_eps_seasons()
    total_movies = stats.get_total_movies()

    total_pages = stats.get_total_book_pages()
    nb_users, nb_media = stats.get_nb_media_and_users()

    stats = MyListsStats(
        nb_users=nb_users,
        nb_media=json.dumps(nb_media),
        total_time=json.dumps(total_time),
        top_media=json.dumps(media_top),
        top_genres=json.dumps(media_genres),
        top_actors=json.dumps(media_actors),
        top_directors=json.dumps(media_directors),
        top_dropped=json.dumps(media_dropped),
        total_episodes=json.dumps(media_eps_seas),
        total_seasons=json.dumps(media_eps_seas),
        total_movies=json.dumps(total_movies),
        top_authors=json.dumps(media_authors),
        top_developers=json.dumps(media_developers),
        total_pages=total_pages,
    )

    # Add and commit changes
    db.session.add(stats)
    db.session.commit()


# ---------------------------------------------------------------------------------------------------------------


def add_cli_commands():
    """ Register the command for the Flask CLI """

    @current_app.cli.command()
    def scheduled_tasks():
        """ Run all the necessary scheduled jobs """

        # Set logger to INFO
        current_app.logger.setLevel(logging.INFO)

        remove_non_list_media()
        remove_all_old_covers()
        automatic_media_refresh()
        add_new_releasing_media()
        automatic_movies_locking()
        compute_media_time_spent()
        update_Mylists_stats()

    @current_app.cli.command()
    def update_igdb_key():
        """ Update the IGDB API key """

        # Set logger to INFO
        current_app.logger.setLevel(logging.INFO)

        update_IGDB_API()
