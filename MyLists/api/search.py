from flask import Blueprint, request, jsonify, abort, current_app
from MyLists.API_data import ApiTMDB, ApiGames, ApiBooks
from MyLists.api.auth import token_auth
from MyLists.models.user_models import User

search_bp = Blueprint("api_search", __name__)


@search_bp.route("/autocomplete", methods=["GET"])
@token_auth.login_required
def autocomplete():
    """ Autocomplete search route for media searching """

    search = request.args.get("q")
    selector = request.args.get("selector")
    page = request.args.get("page", 1, type=int)

    if selector == "users":
        try:
            results = User.create_search_results(search)
        except Exception as e:
            current_app.logger.error(f"[ERROR] - Requesting my DB: {e}")
            return abort(400)
        return jsonify(data=results)

    if selector == "TMDB":
        Api_data = ApiTMDB()
    elif selector == "IGDB":
        Api_data = ApiGames()
    elif selector == "BOOKS":
        Api_data = ApiBooks()
    else:
        return abort(400)

    try:
        Api_data.search(search, page)
        results = Api_data.create_search_results()
    except Exception as e:
        current_app.logger.error(f"[ERROR] - Requesting the API: {e}")
        return abort(400)

    return jsonify(data=results)
