import secrets
from pathlib import Path
from urllib.request import urlretrieve
from PIL import Image
from PIL.Image import Resampling
from flask import current_app
from flask import request, jsonify, Blueprint, abort
from MyLists import db
from MyLists.api.auth import token_auth, current_user
from MyLists.classes.API_data import ApiData
from MyLists.scheduled_tasks.media_refresher import refresh_element_data
from MyLists.utils.decorators import validate_media_type
from MyLists.utils.enums import MediaType, RoleType
from MyLists.utils.utils import get_models_group

details_bp = Blueprint("api_details", __name__)


@details_bp.route("/details/<media_type>/<media_id>", methods=["GET"])
@token_auth.login_required
@validate_media_type
def media_details(media_type: MediaType, media_id: int):
    """ Return the details of a media as well as the user details concerning this media """

    media_class, *_, label_class = get_models_group(media_type)
    is_search = request.args.get("search")

    if is_search:
        media = media_class.query.filter_by(api_id=media_id).first()
        if not media:
            API_class = ApiData.get_API_class(media_type)
            try:
                media = API_class(API_id=media_id).save_media_to_db()
                db.session.commit()
            except Exception as e:
                current_app.logger.error(f"Error trying to add ({media_type.value}) ID [{media_id}] to DB: {e}")
                return {"message": "Sorry, an error occurred loading the media info. Please try again later."}, 400
    else:
        # Check <media> in database
        media = media_class.query.filter_by(id=media_id).first()
        if not media:
            return abort(404, "The media could not be found.")

    data = dict(
        media=media.to_dict(),
        user_data=media.get_user_list_info(label_class),
        follows_data=media.in_follows_lists(),
        redirect=True if is_search else False,
    )

    return jsonify(data=data)


@details_bp.route("/details/form/<media_type>/<media_id>", methods=["GET", "POST"])
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
    if media_type == MediaType.BOOKS and (len(data.get("genres", []) or [])) != 0:
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


@details_bp.route("/details/<media_type>/<job>/<info>", methods=["GET"])
@token_auth.login_required
@validate_media_type
def information(job: str, media_type: MediaType, info: str):
    """ Get information on media (director, tv creator, tv network, actor, developer, or author) """

    media_class, *_ = get_models_group(media_type)

    # Get data associated to information
    media_data = media_class.get_information(job, info)

    data = dict(
        data=media_data,
        total=len(media_data),
    )

    return jsonify(data=data)


@details_bp.route("/details/refresh/<media_type>/<media_id>", methods=["POST"])
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