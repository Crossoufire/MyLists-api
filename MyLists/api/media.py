import secrets
from pathlib import Path
from typing import Any, List
from urllib.request import urlretrieve
from PIL import Image
from PIL.Image import Resampling
from flask import current_app
from flask import request, jsonify, Blueprint, abort
from MyLists import db
from MyLists.API_data import ApiData
from MyLists.api.auth import token_auth, current_user
from MyLists.api.medialist_query import MediaListQuery
from MyLists.models.user_models import UserLastUpdate, get_coming_next
from MyLists.scheduled_tasks.media_refresher import refresh_element_data
from MyLists.utils.decorators import validate_media_type, media_endpoint_decorator
from MyLists.utils.enums import MediaType, RoleType, Status
from MyLists.utils.utils import get_models_group


media_bp = Blueprint("api_media", __name__)


@media_bp.route("/list/<media_type>/<username>", methods=["GET"])
@token_auth.login_required
@validate_media_type
def media_list(media_type: MediaType, username: str):
    """ Media list route (Series, Anime, Movies, Games, and Books) """

    # Check if <user> has access
    user = current_user.check_autorization(username)

    # Add a view on media list to profile
    current_user.set_view_count(user, media_type)

    # Resolve media query
    media_data, pagination = MediaListQuery(user, media_type).return_results()

    # Commit changes
    db.session.commit()

    data = dict(
        user_data=user.to_dict(),
        media_data=media_data,
        pagination=pagination,
        media_type=media_type.value,
    )

    return jsonify(data=data)


@media_bp.route("/details/<media_type>/<media_id>", methods=["GET"])
@token_auth.login_required
@validate_media_type
def media_details(media_type: MediaType, media_id: int):
    """ Return the details of a media """

    media_class, *_ = get_models_group(media_type)

    # Check <media> in database
    media = media_class.query.filter_by(id=media_id).first()
    if not media:
        return abort(404)

    # Check if <current_user> has <media> in his list
    current_user_data = media.get_user_list_info()
    if current_user_data:
        current_user_data["history"] = UserLastUpdate.get_history(media_type, media_id)

    data = dict(
        user_data=current_user_data,
        media=media.to_dict(),
        follows_data=media.in_follows_lists(),
    )

    return jsonify(data=data)

@media_bp.route("/details/form/<media_type>/<media_id>", methods=["GET", "POST"])
@token_auth.login_required
@validate_media_type
def media_details_form(media_type: MediaType, media_id: int):
    """ Post new media details after edition """

    # Only <admin> and <managers> can access
    if current_user.role == RoleType.USER:
        return abort(403)

    # Get models using <media_type>
    media_class, _, media_genre, *_ = get_models_group(media_type)

    # Get <media> and check if exists
    media = media_class.query.filter_by(id=media_id).first()
    if not media:
        return abort(400)

    # Accepted form fields
    forms_fields = media_class.form_only()

    if request.method == "GET":
        # Create dict
        data = {
            "fields": [(k, v) for k, v in media.to_dict().items() if k in forms_fields],
            "genres": media_genre.get_available_genres() if media_type == MediaType.BOOKS else None,
        }

        return jsonify(data=data)

    # Lock media
    media.lock_status = True

    # Get <data> from JSON
    try:
        data = request.get_json()
    except:
        return abort(400)

    # Add genres if BOOKS
    if media_type == MediaType.BOOKS and (len(data.get("genres", []) or 0)) != 0:
        media_genre.replace_genres(data["genres"], media.id)

    # Suppress all non-allowed fields
    try:
        updates = {k: v for (k, v) in data.items() if k in forms_fields}
        updates["image_cover"] = request.get_json().get("image_cover", "") or ""
    except:
        return abort(400)

    # Check media cover update
    if updates["image_cover"] == "":
        picture_fn = media.image_cover
    else:
        picture_fn = secrets.token_hex(8) + ".jpg"
        picture_path = Path(current_app.root_path, f"static/covers/{media_type.value}_covers", picture_fn)
        try:
            urlretrieve(f"{updates['image_cover']}", f"{picture_path}")
            img = Image.open(f"{picture_path}")
            img = img.resize((300, 450), Resampling.LANCZOS)
            img.save(f"{picture_path}", quality=90)
        except Exception as e:
            current_app.logger.error(f"[ERROR] - occurred when updating the media cover with ID [{media.id}]: {e}")
            picture_fn = media.image_cover

    updates["image_cover"] = picture_fn

    # Set new attributes
    for name, value in updates.items():
        setattr(media, name, value)

    # Commit changes
    db.session.commit()

    return jsonify(data={"message": "Media data successfully updated."})


@media_bp.route("/add_media_to_db/<media_type>/<api_media_id>", methods=["POST"])
@token_auth.login_required
@validate_media_type
def add_media_to_db(media_type: MediaType, api_media_id):
    """ Add the <media> to the database if it doesn't exist yet and return the database ID """

    media_class, *_ = get_models_group(media_type)

    # Check <media> in local DB
    media = media_class.query.filter_by(api_id=api_media_id).first()

    # Try to add media from API otherwise
    if not media:
        API_class = ApiData.get_API_class(media_type)
        try:
            media = API_class(API_id=api_media_id).save_media_to_db()
            db.session.commit()
        except Exception as e:
            current_app.logger.error(f"[ERROR] - trying to add ({media_type.value}) ID [{api_media_id}] to DB: {e}")
            return {"message": "Sorry, a problem occurred trying to load the media info. Please try again later."}, 400

    return jsonify(media_id=media.id)


@media_bp.route("/refresh/<media_type>/<media_id>", methods=["POST"])
@token_auth.login_required
@validate_media_type
def refresh_media(media_type: MediaType, media_id: int):
    """ Refresh a unique <media> details if the user role is at least `manager` """

    if current_user.role == RoleType.USER:
        return abort(403)

    media_class, *_ = get_models_group(media_type)

    media = media_class.query.filter_by(id=media_id).first()
    if media is None:
        return {"message": "Impossible to refresh the media data.", "alert": "warning"}, 400

    response = refresh_element_data(media.api_id, media_type)
    if response:
        return {"message": "Successfully updated the metadata of the media.", "alert": "success"}, 200

    return {"message": "You are not authorized.", "alert": "danger"}, 400


@media_bp.route("/details/<media_type>/<job>/<person>", methods=["GET"])
@token_auth.login_required
@validate_media_type
def persons(job: str, media_type: MediaType, person: str):
    """ Get a person's media (director, creator, author, publisher, or actor) """

    media_class, *_ = get_models_group(media_type)

    # Get data associated to person
    data = media_class.get_persons(job, person)

    return jsonify(data=data)


@media_bp.route("/coming_next", methods=["GET"])
@token_auth.login_required
def coming_next():
    """ For current_user, get their coming next dates for <series>, <anime>, <movies>, and <games> """

    data = [{"media_type": mt.value, "items": get_coming_next(mt)}
            for mt in MediaType if (mt != MediaType.ANIME or current_user.add_anime) and
            (mt != MediaType.GAMES or current_user.add_games) and mt != MediaType.BOOKS]

    return jsonify(data=data)


@media_bp.route("/add_media", methods=["POST"])
@token_auth.login_required
@media_endpoint_decorator(type_=None)
def add_media(media_id: int, media_type: MediaType, payload: Any, models: List[db.Model]):
    """ Add a <media> to the current_user """

    # Rename for clarity
    new_status = payload

    # Check if <new_status> was given
    if new_status is None:
        new_status = models[1].DEFAULT_STATUS.value

    # Check <new_status> parameter
    try:
        new_status = Status(new_status)
    except:
        return abort(400)

    # Check <media> not in user list
    in_list = models[1].query.filter_by(user_id=current_user.id, media_id=media_id).first()
    if in_list:
        return abort(400)

    # Check if <media> exists
    media = models[0].query.filter_by(id=media_id).first()
    if not media:
        return abort(400)

    # Add media to user
    new_watched = media.add_media_to_user(new_status, user_id=current_user.id)

    # Commit changes
    db.session.commit()
    current_app.logger.info(f"[User {current_user.id}] {media_type} Added [ID {media_id}] with status: {new_status}")

    # Set last update
    UserLastUpdate.set_last_update(media=media, media_type=media_type, new_status=new_status)

    # Compute new time spent
    in_list = models[1].query.filter_by(user_id=current_user.id, media_id=media_id).first()
    in_list.update_time_spent(new_value=new_watched)

    # Commit changes
    db.session.commit()

    # Return current user media info
    data = media.get_user_list_info()
    data["history"] = UserLastUpdate.get_history(media_type, media_id)

    return jsonify(data=data)


# noinspection PyUnusedLocal
@media_bp.route("/delete_media", methods=["POST"])
@token_auth.login_required
@media_endpoint_decorator(type_=None)
def delete_media(media_id: int, media_type: MediaType, payload: Any, models: List[db.Model]):
    """ Delete a media from the user """

    media = models[1].query.filter_by(user_id=current_user.id, media_id=media_id).first()
    if not media:
        return abort(400)

    # <Games> model don't have total
    try:
        old_total = media.total
    except:
        old_total = media.playtime

    # Add new time spent
    media.update_time_spent(old_value=old_total, new_value=0)

    # Delete media from user list
    db.session.delete(media)

    # Commit changes and log
    db.session.commit()
    current_app.logger.info(f"[User {current_user.id}] {media_type} [ID {media_id}] successfully removed.")

    return {}, 204


@media_bp.route("/update_favorite", methods=["POST"])
@token_auth.login_required
@media_endpoint_decorator(bool)
def update_favorite(media_id: int, media_type: MediaType, payload: Any, models: List[db.Model]):
    """ Add or remove the media as favorite for the current user """

    # Check if <media_id> in user list
    media = models[1].query.filter_by(user_id=current_user.id, media_id=media_id).first()
    if not media:
        return abort(400)

    # Add favorite
    media.favorite = payload

    # Commit changes
    db.session.commit()
    current_app.logger.info(f"[User {current_user.id}] [{media_type}] with ID [{media_id}] changed favorite: {payload}")

    return {}, 204


@media_bp.route("/update_status", methods=["POST"])
@token_auth.login_required
@media_endpoint_decorator(str)
def update_status(media_id: int, media_type: MediaType, payload: Any, models: List[db.Model]):
    """ Update the media status of a user """

    # Check <status> parameter
    try:
        new_status = Status(payload)
    except:
        return abort(400)

    # Get media
    media = models[1].query.filter_by(user_id=current_user.id, media_id=media_id).first()
    if not media:
        return abort(400)

    # Change <status> and get data to compute <last_updates> and <new_time_spent>
    try:
        old_total = media.total
    except:
        old_total = media.playtime
    old_status = media.status

    new_total = media.update_status(new_status)

    # Set last updates
    UserLastUpdate.set_last_update(
        media=media.media,
        media_type=media_type,
        old_status=old_status,
        new_status=new_status,
        old_playtime=old_total,
        new_playtime=new_total
    )

    # Compute new time spent
    media.update_time_spent(old_value=old_total, new_value=new_total)

    # Commit changes
    db.session.commit()
    current_app.logger.info(f"[User {current_user.id}] {media_type}'s category [ID {media_id}] changed to {new_status}")

    return {}, 204


@media_bp.route("/update_metric", methods=["POST"])
@token_auth.login_required
@media_endpoint_decorator(str)
def update_metric(media_id: int, media_type: MediaType, payload: Any, models: List[db.Model]):
    """ Update the media metric (either 'score' or 'feeling') entered by a user """

    # Get <metric_name>
    metric_name = "feeling" if current_user.add_feeling else "score"

    if metric_name == "score":
        # Check <payload> is '---' or between [0-10]
        try:
            if 0 > float(payload) or float(payload) > 10:
                return abort(400)
        except:
            payload = None
    elif metric_name == "feeling":
        # Check <payload> null or between 1 and 4
        try:
            if 0 > int(payload) or int(payload) > 5:
                return abort(400)
        except:
            payload = None
    else:
        return abort(400)

    media = models[1].query.filter_by(user_id=current_user.id, media_id=media_id).first()
    if not media:
        return abort(400)

    # Set new data
    if metric_name == "score":
        media.score = payload
    elif metric_name == "feeling":
        media.feeling = payload

    # Commit changes
    db.session.commit()
    current_app.logger.info(f"[{current_user.id}] [{media_type}] ID {media_id} score/feeling updated to {payload}")

    return {}, 204


@media_bp.route("/update_redo", methods=["POST"])
@token_auth.login_required
@media_endpoint_decorator(int)
def update_redo(media_id: int, media_type: MediaType, payload: Any, models: List[db.Model]):
    """ Update the media redo value for a user """

    # Check <media_redo> is between [0-10]
    if 0 > payload > 10:
        return abort(400)

    media = models[1].query.filter_by(user_id=current_user.id, media_id=media_id).first()
    if not media or media.status != Status.COMPLETED:
        return abort(400)

    # Update redo and total data done
    old_total = media.total
    new_total = media.update_total_watched(payload)

    # Compute new time spent
    media.update_time_spent(old_value=old_total, new_value=new_total)

    # Commit changes
    db.session.commit()
    current_app.logger.info(f"[{current_user.id}] Media ID {media_id} [{media_type}] rewatched {payload}x times")

    return {}, 204


@media_bp.route("/update_comment", methods=["POST"])
@token_auth.login_required
@media_endpoint_decorator(str)
def update_comment(media_id: int, media_type: MediaType, payload: Any, models: List[db.Model]):
    """ Update the media comment for a user """

    # Check if <media> is <current_user> list
    media = models[1].query.filter_by(user_id=current_user.id, media_id=media_id).first()
    if media is None:
        return abort(400)

    # Update comment
    media.comment = payload

    # Commit changes
    db.session.commit()
    current_app.logger.info(f"[{current_user.id}] updated a comment on {media_type} with ID [{media_id}]")

    return {}, 204


@media_bp.route("/update_playtime", methods=["POST"])
@token_auth.login_required
@media_endpoint_decorator(int)
def update_playtime(media_id: int, media_type: MediaType, payload: Any, models: List[db.Model]):
    """ Update playtime of an updated game from a user """

    # Get in minutes
    new_playtime = payload * 60

    # Check negative playtime
    if new_playtime < 0:
        return abort(400)

    media = models[1].query.filter_by(user_id=current_user.id, media_id=media_id).first()
    if not media:
        return abort(400)

    # Set last updates
    UserLastUpdate.set_last_update(
        media=media.media,
        media_type=media_type,
        old_playtime=media.playtime,
        new_playtime=new_playtime,
        old_status=media.status
    )

    # Compute new time spent
    media.update_time_spent(old_value=media.playtime, new_value=new_playtime)

    # Update new playtime
    media.playtime = new_playtime

    # Commit changes
    db.session.commit()
    current_app.logger.info(f"[{current_user.id}] Games ID {media_id} playtime updated to {new_playtime}")

    return {}, 204


@media_bp.route("/update_season", methods=["POST"])
@token_auth.login_required
@media_endpoint_decorator(int)
def update_season(media_id: int, media_type: MediaType, payload: Any, models: List[db.Model]):
    """ Update the season of an updated anime or series for the user """

    # Check if <media> exists
    media = models[1].query.filter_by(user_id=current_user.id, media_id=media_id).first()
    if not media:
        return abort(400)

    # Check if season number is between 1 and <last_season>
    if 1 > payload or payload > media.media.eps_per_season[-1].season:
        return abort(400)

    # Get old data
    old_season = media.current_season
    old_episode = media.last_episode_watched
    old_total = media.total

    # Set new data
    new_watched = sum([x.episodes for x in media.media.eps_per_season[:payload-1]]) + 1
    media.current_season = payload
    media.last_episode_watched = 1
    new_total = new_watched + (media.rewatched * media.media.total_episodes)
    media.total = new_total

    # Set last updates
    UserLastUpdate.set_last_update(
        media=media.media,
        media_type=media_type,
        old_season=old_season,
        new_season=payload,
        new_episode=1,
        old_episode=old_episode
    )

    # Compute new time spent
    media.update_time_spent(old_value=old_total, new_value=new_total)

    # Commit changes
    db.session.commit()
    current_app.logger.info(f"[User {current_user.id}] - [{media_type}] - [ID {media_id}] season updated to {payload}")

    return {}, 204


@media_bp.route("/update_episode", methods=["POST"])
@token_auth.login_required
@media_endpoint_decorator(int)
def update_episode(media_id: int, media_type: MediaType, payload: Any, models: List[db.Model]):
    """ Update the episode of an updated anime or series from a user """

    # Check if media exists
    media = models[1].query.filter_by(user_id=current_user.id, media_id=media_id).first()
    if not media:
        return abort(400)

    # Check if episode number between 1 and <last_episode>
    if 1 > payload or payload > media.media.eps_per_season[media.current_season-1].episodes:
        return abort(400)

    # Get old data
    old_season = media.current_season
    old_episode = media.last_episode_watched
    old_total = media.total

    # Set new data
    new_watched = sum([x.episodes for x in media.media.eps_per_season[:old_season-1]]) + payload
    media.last_episode_watched = payload
    new_total = new_watched + (media.rewatched * media.media.total_episodes)
    media.total = new_total

    # Set last updates
    UserLastUpdate.set_last_update(
        media=media.media,
        media_type=media_type,
        old_season=old_season,
        new_season=old_season,
        old_episode=old_episode,
        new_episode=payload
    )

    # Compute new time spent
    media.update_time_spent(old_value=old_total, new_value=new_total)

    # Commit changes
    db.session.commit()
    current_app.logger.info(f"[User {current_user.id}] {media_type} [ID {media_id}] episode updated to {payload}")

    return {}, 204


@media_bp.route("/update_page", methods=["POST"])
@token_auth.login_required
@media_endpoint_decorator(int)
def update_page(media_id: int, media_type: MediaType, payload: Any, models: List[db.Model]):
    """ Update the page read of an updated book from a user """

    # Check if media exists
    media = models[1].query.filter_by(user_id=current_user.id, media_id=media_id).first()
    if not media:
        return abort(400)

    # Check page value
    if payload > int(media.media.pages) or payload < 0:
        return abort(400)

    # Get old data
    old_page = media.actual_page
    old_total = media.total

    # Set new data
    media.actual_page = payload
    new_total = payload + (media.rewatched * media.media.pages)
    media.total = new_total

    # Set last updates
    UserLastUpdate.set_last_update(
        media=media.media,
        media_type=media_type,
        old_page=old_page,
        new_page=payload,
        old_status=media.status
    )

    # Compute new time spent
    media.update_time_spent(old_value=old_total, new_value=new_total)

    # Commit changes
    db.session.commit()
    current_app.logger.info(f"[User {current_user.id}] {media_type} [ID {media_id}] page updated from {old_page} to {payload}")

    return {}, 204


@media_bp.route("/lock_media", methods=["POST"])
@token_auth.login_required
@media_endpoint_decorator(bool)
def lock_media(media_id: int, media_type: MediaType, payload: Any, models: List[db.Model]):
    """ Lock a media so the API does not update it anymore """

    # Check user > user role
    if current_user.role == RoleType.USER:
        return abort(400)

    # Check if media exists
    media = models[0].query.filter_by(id=media_id).first()
    if not media:
        return abort(400)

    # Lock media
    media.lock_status = payload

    # Commit changes
    db.session.commit()
    current_app.logger.info(f"{media_type} [ID {media_id}] successfully locked.")

    return {}, 204
