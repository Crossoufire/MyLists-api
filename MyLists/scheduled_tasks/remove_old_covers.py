import os
from pathlib import Path
from flask import current_app
from MyLists.models.books_models import Books
from MyLists.models.games_models import Games
from MyLists.models.movies_models import Movies
from MyLists.models.tv_models import Series, Anime


def _remove_old_series_covers():
    """ Remove all the series old covers on disk if they are not present in the database """

    path_series_covers = Path(current_app.root_path, "static/covers/series_covers/")

    images_in_db = [media.image_cover for media in Series.query.all()]

    # Filter out images that need to be removed
    images_to_remove = [file for file in os.listdir(path_series_covers) if file not in images_in_db]

    # Delete old series covers and log info
    count = 0
    for image in images_to_remove:
        file_path = path_series_covers / image
        try:
            os.remove(file_path)
            current_app.logger.info(f"Removed old series cover with name ID: {image}")
            count += 1
        except Exception as e:
            current_app.logger.error(f"Error occurred while deleting this old series cover {image}: {e}")
    current_app.logger.info(f'Total old series old covers deleted: {count}')

def _remove_old_anime_covers():
    """ Remove all the anime old covers on disk if they are not present in the database """

    path_anime_covers = Path(current_app.root_path, "static/covers/anime_covers/")

    images_in_db = [media.image_cover for media in Anime.query.all()]

    # Filter out images that need to be removed
    images_to_remove = [file for file in os.listdir(path_anime_covers) if file not in images_in_db]

    # Delete old anime covers and log info
    count = 0
    for image in images_to_remove:
        file_path = path_anime_covers / image
        try:
            os.remove(file_path)
            current_app.logger.info(f"Removed old anime cover with name ID: {image}")
            count += 1
        except Exception as e:
            current_app.logger.error(f"Error occurred while deleting this old anime cover {image}: {e}")
    current_app.logger.info(f'Total old anime old covers deleted: {count}')

def _remove_old_movies_covers():
    """ Remove all the movies old covers on disk if they are not present in the database """

    path_movies_covers = Path(current_app.root_path, "static/covers/movies_covers/")

    images_in_db = [media.image_cover for media in Movies.query.all()]

    # Filter out images that need to be removed
    images_to_remove = [file for file in os.listdir(path_movies_covers) if file not in images_in_db]

    # Delete old movies covers and log info
    count = 0
    for image in images_to_remove:
        file_path = path_movies_covers / image
        try:
            os.remove(file_path)
            current_app.logger.info(f"Removed old movie cover with name ID: {image}")
            count += 1
        except Exception as e:
            current_app.logger.error(f"Error occurred while deleting this old movie cover {image}: {e}")
    current_app.logger.info(f'Total old movies old covers deleted: {count}')

def _remove_old_books_covers():
    """ Remove all the books old covers on disk if they are not present in the database """

    path_books_covers = Path(current_app.root_path, "static/covers/books_covers/")

    images_in_db = [media.image_cover for media in Books.query.all()]

    # Filter out images that need to be removed
    images_to_remove = [file for file in os.listdir(path_books_covers) if file not in images_in_db]

    # Delete old books covers and log info
    count = 0
    for image in images_to_remove:
        file_path = path_books_covers / image
        try:
            os.remove(file_path)
            current_app.logger.info(f"Removed old book cover with name ID: {image}")
            count += 1
        except Exception as e:
            current_app.logger.error(f"Error occurred while deleting this old book cover {image}: {e}")
    current_app.logger.info(f'Total old books old covers deleted: {count}')

def _remove_old_games_covers():
    """ Remove all the games old covers on disk if they are not present in the database """

    path_games_covers = Path(current_app.root_path, "static/covers/games_covers/")

    images_in_db = [media.image_cover for media in Games.query.all()]

    # Filter out images that need to be removed
    images_to_remove = [file for file in os.listdir(path_games_covers) if file not in images_in_db]

    # Delete old games covers and log info
    count = 0
    for image in images_to_remove:
        file_path = path_games_covers / image
        try:
            os.remove(file_path)
            current_app.logger.info(f"Removed old game cover with name ID: {image}")
            count += 1
        except Exception as e:
            current_app.logger.error(f"Error occurred while deleting this old game cover {image}: {e}")
    current_app.logger.info(f'Total old games old covers deleted: {count}')


