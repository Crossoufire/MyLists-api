# MyLists backend API

[MyLists](https://mylists.info) is a website with a nice and clear interface for you to list all the series, anime, 
movies, games and books you've watched/read/played. It regroups the functionalities of different site in one.
It integrates statistics like: watched time, comments, favorites and more. 
You can follow people, see their lists and compare it to yours. 

Live version here: [https://mylists.info](https://mylists.info).

This backend uses [Flask](https://flask.palletsprojects.com/).

# Features

* Create a list for all your series, anime, movies, games and books. 
* Get statistics about your lists (Time spent, number of episodes watched, prefered genres, etc...)
* Get informed of your next series, anime and movies to airs.
* Follows your friends and get updates.
* Compare your lists with your follows.
* Notifications system
* More to come!

# Prerequisites

* Python 3.9+
* pip
* WSL2 if using Windows for the local test of `scheduled-tasks`

# Installation
First install python and create a virtual env:
```
pip install virtual-env
python -m venv venv-mylists
```
Then clone this repo and install the requirements:
```
git clone https://www.github.com/Crossoufire/MyLists-api.git
cd MyLists
pip install -r requirements.txt
```

## Setup the .flaskenv and the .env file
- In the `.flaskenv` setup the `FLASK_DEBUG` to either `0` or `1` (default to `1`).
- Create a `.env` file:
```
SECRET_KEY=<change-me>

MAIL_SERVER=<your-mail-server>
MAIL_PORT=<port>
MAIL_USE_TLS=<True|False>
MAIL_USE_SSL=<True|False>
MAIL_USERNAME=<mail@mail.com>
MAIL_PASSWORD=<password>

THEMOVIEDB_API_KEY=<themoviedb-api-key>
GOOGLE_BOOKS_API_KEY=<google-books-api-key>
CLIENT_IGDB=<igdb-client-id>
SECRET_IGDB=<igdb-secret>
IGDB_API_KEY=<igdb-api-key>
```

Then run the command `python mylists.py`. The API backend will be served at [http://localhost:5000](http://localhost:5000).

## Contact
<contact.us.at.mylists@gamil.com>
