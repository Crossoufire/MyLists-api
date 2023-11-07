from datetime import datetime
from flask import current_app
from MyLists import db
from MyLists.API_data import ApiData, ApiTV, ApiMovies
from MyLists.models.games_models import Games
from MyLists.models.movies_models import Movies
from MyLists.models.tv_models import (Series, Anime, SeriesList, AnimeList, SeriesEpisodesPerSeason,
                                      AnimeEpisodesPerSeason)
from MyLists.utils.enums import MediaType
from typing import Tuple, List, Dict


def refresh_element_data(api_id: int, media_type: MediaType):
    """ Refresh a media using appropriate API """

    ApiModel = ApiData.get_API_class(media_type)
    data = ApiModel(API_id=api_id).update_media_data()

    # Update main details for each media
    if media_type == MediaType.SERIES:
        Series.query.filter_by(api_id=api_id).update(data["media_data"])
    elif media_type == MediaType.ANIME:
        Anime.query.filter_by(api_id=api_id).update(data["media_data"])
    elif media_type == MediaType.MOVIES:
        Movies.query.filter_by(api_id=api_id).update(data["media_data"])
    elif media_type == MediaType.GAMES:
        Games.query.filter_by(api_id=api_id).update(data["media_data"])

    # Commit changes
    db.session.commit()

    # Check episodes/seasons
    if media_type in (MediaType.SERIES, MediaType.ANIME):
        if media_type == MediaType.SERIES:
            media = Series.query.filter_by(api_id=api_id).first()
            old_seas_eps = [n.episodes for n in SeriesEpisodesPerSeason.query.filter_by(media_id=media.id).all()]
        elif media_type == MediaType.ANIME:
            media = Anime.query.filter_by(api_id=api_id).first()
            old_seas_eps = [n.episodes for n in AnimeEpisodesPerSeason.query.filter_by(media_id=media.id).all()]
        else:
            return False

        new_seas_eps = [d["episodes"] for d in data["seasons_data"]]

        if new_seas_eps != old_seas_eps:
            if media_type == MediaType.SERIES:
                users_list = SeriesList.query.filter_by(media_id=media.id).all()

                for user in users_list:
                    episodes_watched = user.total

                    count = 0
                    for i in range(0, len(data["seasons_data"])):
                        count += data["seasons_data"][i]["episodes"]
                        if count == episodes_watched:
                            user.last_episode_watched = data["seasons_data"][i]["episodes"]
                            user.current_season = data['seasons_data'][i]['season']
                            break
                        elif count > episodes_watched:
                            user.last_episode_watched = data["seasons_data"][i]["episodes"] - (count - episodes_watched)
                            user.current_season = data["seasons_data"][i]["season"]
                            break
                        elif count < episodes_watched:
                            try:
                                data['seasons_data'][i + 1]["season"]
                            except IndexError:
                                user.last_episode_watched = data["seasons_data"][i]["episodes"]
                                user.current_season = data["seasons_data"][i]["season"]
                                break

                SeriesEpisodesPerSeason.query.filter_by(media_id=media.id).delete()
                db.session.commit()

                for seas in data["seasons_data"]:
                    # noinspection PyArgumentList
                    season = SeriesEpisodesPerSeason(
                        media_id=media.id,
                        season=seas["season"],
                        episodes=seas["episodes"]
                    )
                    db.session.add(season)
                db.session.commit()
            elif media_type == MediaType.ANIME:
                users_list = AnimeList.query.filter_by(media_id=media.id).all()

                for user in users_list:
                    episodes_watched = user.total

                    count = 0
                    for i in range(0, len(data["seasons_data"])):
                        count += data["seasons_data"][i]["episodes"]
                        if count == episodes_watched:
                            user.last_episode_watched = data["seasons_data"][i]["episodes"]
                            user.current_season = data["seasons_data"][i]["season"]
                            break
                        elif count > episodes_watched:
                            user.last_episode_watched = data["seasons_data"][i]["episodes"] - (count - episodes_watched)
                            user.current_season = data["seasons_data"][i]['season']
                            break
                        elif count < episodes_watched:
                            try:
                                data["seasons_data"][i + 1]["season"]
                            except IndexError:
                                user.last_episode_watched = data["seasons_data"][i]["episodes"]
                                user.current_season = data["seasons_data"][i]["season"]
                                break

                AnimeEpisodesPerSeason.query.filter_by(media_id=media.id).delete()
                db.session.commit()

                for seas in data["seasons_data"]:
                    # noinspection PyArgumentList
                    season = AnimeEpisodesPerSeason(
                        media_id=media.id,
                        season=seas["season"],
                        episodes=seas["episodes"]
                    )
                    db.session.add(season)
                db.session.commit()

    return True


def _fetch_all_api_ids() -> Tuple[List[int], List[int], List[int], List[int]]:
    """ The api id from the database """

    # Fetch all API ids
    all_series_api_id = [m[0] for m in db.session.query(Series.api_id).filter(Series.lock_status != True)]
    all_anime_api_id = [m[0] for m in db.session.query(Anime.api_id).filter(Anime.lock_status != True)]
    all_movies_api_id = [m[0] for m in db.session.query(Movies.api_id).filter(Movies.lock_status != True)]

    all_games = Games.query.all()
    all_games_api_id = []
    for game in all_games:
        try:
            if datetime.utcfromtimestamp(int(game.release_date)) > datetime.now():
                all_games_api_id.append(game.api_id)
        except:
            all_games_api_id.append(game.api_id)

    return all_series_api_id, all_anime_api_id, all_movies_api_id, all_games_api_id


def _refresh_tv(tv_ids: List[int], all_id_tv_changes: Dict, media_type: MediaType):
    """ Refresh the series/anime local data using TMDB API """

    # Refresh Series/Anime
    for result in all_id_tv_changes["results"]:
        tmdb_id = result["id"]
        if tmdb_id in tv_ids:
            try:
                refresh_element_data(tmdb_id, media_type)
                current_app.logger.info(f"[INFO] - Refreshed the series/anime with TMDB ID = [{tmdb_id}]")
            except Exception as e:
                current_app.logger.info(f"[ERROR] - While refreshing the series/anime with ID = [{tmdb_id}]: {e}")


def _refresh_movies(movies_ids: List[int]):
    """ Refresh the movies local data using TMDB API """

    # From TMDB API, Fetch all changed Movies IDs
    try:
        all_id_movies_changes = ApiMovies().get_changed_data()
    except Exception as e:
        all_id_movies_changes = {"results": []}
        current_app.logger.error(f"[ERROR] - Requesting the changed IDs for the movies from the TMDB API: {e}")

    # Refresh movies
    for result in all_id_movies_changes["results"]:
        tmdb_id = result["id"]
        if tmdb_id in movies_ids:
            try:
                refresh_element_data(tmdb_id, MediaType.MOVIES)
                current_app.logger.info(f"[INFO] - Refreshed the movie with TMDB ID: [{tmdb_id}]")
            except Exception as e:
                current_app.logger.info(f"[ERROR] - While refreshing the movies with TMDB ID = [{tmdb_id}]: {e}")


def _refresh_games(games_ids: List[int]):
    """ Refresh the games local data using the IGDB API """

    # Refresh Games
    for api_id in games_ids:
        try:
            refresh_element_data(api_id, MediaType.GAMES)
            current_app.logger.info(f"[INFO] - Refreshed the game with IGDB ID: [{api_id}]")
        except Exception as e:
            current_app.logger.info(f"[ERROR] - While refreshing games with IGDB ID = [{api_id}]: {e}")


def automatic_media_refresh():
    """ Automatically refresh the media using the appropriate API """

    current_app.logger.info("###############################################################################")
    current_app.logger.info("[SYSTEM] - Starting automatic media refresh -")

    # Fetch all IDs
    series_ids, anime_ids, movies_ids, games_ids = _fetch_all_api_ids()

    # From TMDB API, Fetch all changed TV IDs
    try:
        all_id_tv_changes = ApiTV().get_changed_data()
    except Exception as e:
        all_id_tv_changes = {"results": []}
        current_app.logger.error(f"[ERROR] - Requesting the changed IDs for the series/anime from the TMDB API: {e}")

    _refresh_tv(series_ids, all_id_tv_changes, MediaType.SERIES)
    _refresh_tv(anime_ids, all_id_tv_changes, MediaType.ANIME)
    _refresh_movies(movies_ids)
    _refresh_games(games_ids)

    current_app.logger.info("[SYSTEM] - Finished Automatic media refresh -")
    current_app.logger.info('###############################################################################')