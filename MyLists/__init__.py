import email.utils as em
import logging
import os
import smtplib
from email.message import EmailMessage
from logging.handlers import SMTPHandler, RotatingFileHandler
from flask import Flask
from flask_bcrypt import Bcrypt
from flask_caching import Cache
from flask_cors import CORS
from flask_mail import Mail
from flask_sqlalchemy import SQLAlchemy
from MyLists.utils.enums import RoleType
from config import Config


# Globally accessible Flask modules
config = Config()
mail = Mail()
db = SQLAlchemy()
bcrypt = Bcrypt()
cache = Cache()
cors = CORS()


class SSL_SMTPHandler(SMTPHandler):
    """ Create an inherited class of SMTPHandler which handle SSL """

    def emit(self, record):
        """ Emit a record """

        try:
            port = self.mailport
            if not port:
                port = smtplib.SMTP_PORT
            smtp = smtplib.SMTP_SSL(self.mailhost, port, timeout=self.timeout)

            # Create message
            msg = EmailMessage()
            msg["From"] = self.fromaddr
            msg["To"] = ",".join(self.toaddrs)
            msg["Subject"] = self.getSubject(record)
            msg["Date"] = em.localtime()
            msg.set_content(self.format(record))

            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(msg, self.fromaddr, self.toaddrs)
            smtp.quit()
        except (KeyboardInterrupt, SystemExit):
            raise Exception
        except:
            self.handleError(record)


def _import_blueprints(app: Flask):
    """ Import and register blueprints to the app """

    # Import API blueprints
    from MyLists.api.tokens import tokens as api_tokens_bp
    from MyLists.api.users import users as api_users_bp
    from MyLists.api.media import media_bp as api_media_bp
    from MyLists.api.search import search_bp as api_search_bp
    from MyLists.api.general import general as api_general_bp
    from MyLists.api.errors import errors as api_errors_bp

    # Blueprints list
    api_blueprints = [api_tokens_bp, api_users_bp, api_media_bp, api_search_bp, api_general_bp, api_errors_bp]

    # Register blueprints
    for blueprint in api_blueprints:
        app.register_blueprint(blueprint, url_prefix="/api")


def _create_app_logger(app: Flask):
    """ Create an app logger and an <SSL_SMTPHandler> class for sending errors to the admin """

    log_file_path = "MyLists/static/log/mylists.log"

    # Check if log file exists, if not, create it
    if not os.path.exists(log_file_path):
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
        open(log_file_path, "w").close()

    handler = RotatingFileHandler(log_file_path, maxBytes=3000000, backupCount=15)
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s"))
    handler.setLevel(logging.INFO)
    app.logger.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.logger.info("MyLists is starting up...")


def _create_mail_handler(app: Flask):
    """ Create a mail handler from the <SSL_SMTPHandler> class """

    mail_handler = SSL_SMTPHandler(
        mailhost=(app.config["MAIL_SERVER"], app.config["MAIL_PORT"]),
        fromaddr=app.config["MAIL_USERNAME"],
        toaddrs=app.config["MAIL_USERNAME"],
        subject="MyLists - Exceptions occurred",
        credentials=(app.config["MAIL_USERNAME"], app.config["MAIL_PASSWORD"])
    )

    # Set logger level to ERROR only
    mail_handler.setLevel(logging.ERROR)
    app.logger.addHandler(mail_handler)


def _create_first_db_data():
    """ Create all the db tables the first time and add the first data to the database """

    from MyLists.models.user_models import User
    from datetime import datetime
    from MyLists.scheduled_tasks.scheduled_tasks import compute_media_time_spent
    from MyLists.models.utils_models import Badges, Ranks

    # Create all DB tables - does not update existing tables
    db.create_all()

    # Create an <admin>, a <manager> and a <user> if <admin> does not exist
    if User.query.filter_by(id="1").first() is None:
        admin1 = User(
            username="admin",
            email="admin@admin.com",
            password=bcrypt.generate_password_hash("password").decode("utf-8"),
            active=True,
            private=True,
            registered_on=datetime.utcnow(),
            activated_on=datetime.utcnow(),
            role=RoleType.ADMIN,
        )
        manager1 = User(
            username="manager",
            email="manager@manager.com",
            password=bcrypt.generate_password_hash("password").decode("utf-8"),
            active=True,
            registered_on=datetime.utcnow(),
            activated_on=datetime.utcnow(),
            role=RoleType.MANAGER,
        )
        user1 = User(
            username="user",
            email="user@user.com",
            password=bcrypt.generate_password_hash("password").decode("utf-8"),
            active=True,
            registered_on=datetime.utcnow(),
            activated_on=datetime.utcnow(),
        )

        db.session.add_all([admin1, manager1, user1])

        # update_Mylists_stats()
        # update_IGDB_API()
        Badges.add_badges_to_db()
        Ranks.add_ranks_to_db()

    # Refresh badges, ranks and compute time spent for each user
    Badges.refresh_db_badges()
    Ranks.refresh_db_ranks()
    compute_media_time_spent()

    # Commit changes
    db.session.commit()


def init_app() -> Flask:
    """ Initialize the core application """

    # Fetch Flask app name (.flaskenv) and check config from <.env> file
    app = Flask(__name__, static_url_path="/api/static")
    app.config.from_object(config)
    app.url_map.strict_slashes = False

    # Initialize modules
    mail.init_app(app)
    db.init_app(app)
    bcrypt.init_app(app)
    cache.init_app(app)
    cors.init_app(
        app,
        origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8080", "http://127.0.0.1:8080"],
        supports_credentials=True,
    )

    with app.app_context():
        _import_blueprints(app)

        if not app.debug:
            _create_app_logger(app)
            _create_mail_handler(app)

        # Import CLI commands from <scheduled_tasks>
        from MyLists.scheduled_tasks.scheduled_tasks import add_cli_commands
        add_cli_commands()

        # Import first data and populate DB
        _create_first_db_data()

        return app
