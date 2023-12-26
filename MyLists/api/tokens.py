from __future__ import annotations
from datetime import datetime
from typing import Tuple, Dict
from flask import Blueprint, request, abort, url_for, current_app
from flask_bcrypt import generate_password_hash
from werkzeug.http import dump_cookie
from MyLists import db
from MyLists.api.auth import basic_auth, current_user
from MyLists.api.email import send_email
from MyLists.models.user_models import Token, User


tokens = Blueprint("api_tokens", __name__)


def token_response(token: Token) -> Tuple[Dict, int, Dict]:
    """ Generate the token response and send it to the user """

    headers = {
        "Set-Cookie": dump_cookie(
            key="refresh_token",
            value=token.refresh_token,
            path=url_for("api_tokens.new_token"),
            secure=True,
            httponly=True,
            samesite="none",
        ),
    }

    return {"access_token": token.access_token}, 200, headers


@tokens.route("/tokens", methods=["POST"])
@basic_auth.login_required
def new_token():
    """ Create an <access token> and a <refresh token>. The <refresh token> is returned as a hardened cookie """

    # Check user active
    if not current_user.active:
        return {"message": "Your account is not activated, please check your email."}, 401

    # Generate <access token> and <refresh token>
    token = current_user.generate_auth_token()

    # Add token to db
    db.session.add(token)

    # Clean Token table from old tokens
    Token.clean()

    # Commit changes
    db.session.commit()

    return token_response(token)


@tokens.route("/tokens", methods=["PUT"])
def refresh():
    """ Refresh an <access token>. The client needs to pass the <refresh token> in a `refresh_token` cookie.
    The <access token> must be passed in the request body """

    # Get <access token> and <refresh token>
    access_token = request.get_json().get("access_token")
    refresh_token = request.cookies.get("refresh_token")

    if not access_token or not refresh_token:
        return abort(401)

    token = User.verify_refresh_token(refresh_token, access_token)
    if token is None:
        return abort(401)

    # Token now expired
    token.expire()

    # Create new <access token> and <refresh token>
    new_token_ = token.user.generate_auth_token()

    # Add all and commit changes
    db.session.add_all([token, new_token_])
    db.session.commit()

    return token_response(new_token_)


@tokens.route("/tokens", methods=["DELETE"])
def revoke_token():
    """ Revoke an access token = logout """

    # Get <access token> from header
    access_token = request.headers["Authorization"].split()[1]

    # Fetch <access token> in database
    token = Token.query.filter_by(access_token=access_token).first()
    if not token:
        return abort(401)

    # Token is now expired
    token.expire()

    # Commit changes
    db.session.commit()

    return {}, 204


@tokens.route("/tokens/reset_password_token", methods=["POST"])
def reset_password_token():
    """ Generate a password reset token and send the mail to the user """

    try:
        data = request.get_json()
    except:
        return abort(400)

    # Necessary fields
    fields = ["email", "callback"]

    if not all(f in data for f in fields):
        return {"message": f"Not all fields included: {', '.join(fields)}"}, 400

    # Check user
    user = User.query.filter_by(email=data["email"]).first()

    if not user:
        return {"message": "Sorry, but this email is not associated to an account."}, 404

    if not user.active:
        return {"message": "Sorry, but this account is not activated."}, 404

    # Send email to user
    try:
        send_email(
            user=user,
            subject="Password Reset Request",
            template="password_reset",
            callback=data["callback"],
        )
    except Exception as e:
        current_app.logger.error(f"ERROR sending an email to account [{user.id}]: {e}")
        return {"message": "An error occurred while sending the email. Please try again later."}, 404

    return {"message": "An email was send for you to change your password."}, 200


@tokens.route("/tokens/reset_password", methods=["POST"])
def reset_password():
    """ Check password token and change user password """

    try:
        data = request.get_json()
    except:
        return abort(400)

    # Check user token
    user = User.verify_jwt_token(data["token"])

    # Check if user active
    if not user or not user.active:
        return {"message": "This is an invalid or an expired token."}, 400

    # Add new password
    user.password = generate_password_hash(data.get("new_password"))

    # Commit changes
    db.session.commit()

    # Log info
    current_app.logger.info(f"[INFO] - [{user.id}] Password changed.")

    return {"message": "Your password was successfully modified."}, 200


@tokens.route("/tokens/register_token", methods=["POST"])
def register_token():
    """ Check the register token to validate a new user account """

    try:
        token = request.get_json()["token"]
    except:
        return abort(400)

    # Check user token
    user = User.verify_jwt_token(token)

    # Check if user active
    if not user or user.active:
        return {"message": "This is an invalid or an expired token."}, 400

    # Add information
    user.active = True
    user.activated_on = datetime.utcnow()

    # Commit changes
    db.session.commit()

    # Log info
    current_app.logger.info(f"[INFO] - [{user.id}] Account activated.")

    return {"message": "Your account has been activated."}, 200