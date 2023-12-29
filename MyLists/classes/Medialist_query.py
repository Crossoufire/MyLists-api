from typing import Tuple, Dict, Any
from flask import abort, request
from sqlalchemy import asc, or_
from MyLists import db
from MyLists.api.auth import current_user
from MyLists.models.user_models import User
from MyLists.utils.enums import Status, MediaType
from MyLists.utils.utils import get_models_group


class BaseMediaQuery:
    """ Base class for the common functionality of the queries and initialization """

    PER_PAGE: int = 36

    def __init__(self, user: User, media_type: MediaType):
        self.user = user
        self.media_type = media_type

        # Fetch models corresponding to <media_type>
        media, media_list, media_genre, *media_mores = get_models_group(media_type)
        self.media = media
        self.media_list = media_list
        self.media_genre = media_genre
        self.media_mores = media_mores

        # Fetch <args> from request
        self.search = request.args.get("search")
        self.sorting = request.args.get("sorting", media_list.DEFAULT_SORTING)
        self.status = request.args.get("status", media_list.DEFAULT_STATUS)
        self.show_common = request.args.get("showCommon", "true", type=str)
        self.genre = request.args.get("genre", "All", type=str)
        self.lang = request.args.get("lang", "All", type=str)
        self.page = request.args.get("page", 1, type=int)

        # Common media
        self.total_media = 0
        self.common_ids = []
        if current_user.id != self.user.id:
            self._compute_total_and_commons()

        # Predefined attributes
        self.results = []
        self.pages = 0
        self.total = 0

        # Pagination
        self.all_status = self.media_list.Status.to_list(extra=True)
        self.all_genres = self.media_genre.get_available_genres()
        self.all_sorting = self.media_list.get_available_sorting(self.user.add_feeling)

    def _get_sorting(self) -> Any:
        """ Get the sorting possibilities and sort the query """

        # Check sorting
        try:
            sort_filter = self.all_sorting[self.sorting]
        except KeyError:
            return abort(400, "This sorting is not defined.")

        return sort_filter

    def _get_status_filter(self) -> Any:
        """ Get the status filter from the query """

        # Status Filtering
        try:
            status = Status(self.status)
            status_filter = True
            if status not in (Status.FAVORITE, Status.SEARCH, Status.ALL):
                status_filter = (self.media_list.status == status)
            elif status == Status.FAVORITE:
                status_filter = (self.media_list.favorite == True)
        except ValueError:
            return abort(400, "This status does not exists.")

        return status_filter

    def _get_lang_filter(self) -> Any:
        """ Get the lang filter from the query """

        lang_filter = True
        if self.media_type == MediaType.MOVIES:
            lang_filter = self.media.original_language.like(self.lang) if self.lang != "All" else True

        return lang_filter

    def _get_common_filter(self) -> Any:
        """ Get the common ids between the current user and other list """
        return self.media_list.media_id.notin_(self.common_ids) if self.show_common == "false" else True

    def _compute_total_and_commons(self):
        """ Get the total quantity of media and the common media/ids """

        # Count total media
        self.total_media = (db.session.query(self.media_list.media_id)
                            .filter(self.media_list.user_id == self.user.id).count())

        # Check TOTAL COMMONS
        sub_q = db.session.query(self.media_list.media_id).filter(self.media_list.user_id == current_user.id)

        common_ids = db.session.query(self.media_list.media_id).filter(
            self.media_list.user_id == self.user.id, self.media_list.media_id.in_(sub_q)).all()

        self.common_ids = [data[0] for data in common_ids]

class SearchMediaQuery(BaseMediaQuery):
    """ Subclass for handling the search query part """

    def _search_query(self):
        """ Execute the search query on a <media_list> for a specified <user> """

        # First query part
        query_part = (db.session.query(self.media_list)
                      .outerjoin(self.media, self.media.id == self.media_list.media_id)
                      .outerjoin(self.media_genre, self.media_genre.media_id == self.media.id))

        # Selection depending on <media_type>
        if self.media_type in (MediaType.SERIES, MediaType.ANIME):
            query_part = query_part.outerjoin(self.media_mores[1], self.media_mores[1].media_id == self.media.id)
            query_part = query_part.outerjoin(self.media_mores[2], self.media_mores[2].media_id == self.media.id)
            search_filter = or_(
                self.media.name.ilike(f"%{self.search}%"),
                self.media.original_name.ilike(f"%{self.search}%"),
                self.media_mores[1].network.ilike(f"%{self.search}%"),
                self.media_mores[2].name.ilike(f"%{self.search}%"),
            )
        elif self.media_type == MediaType.MOVIES:
            query_part = query_part.outerjoin(self.media_mores[0], self.media_mores[0].media_id == self.media.id)
            search_filter = or_(
                self.media.name.ilike(f"%{self.search}%"),
                self.media.original_name.ilike(f"%{self.search}%"),
                self.media.director_name.ilike(f"%{self.search}%"),
                self.media_mores[0].name.ilike(f"%{self.search}%"),
            )
        elif self.media_type == MediaType.GAMES:
            query_part = query_part.outerjoin(self.media_mores[0], self.media_mores[0].media_id == self.media.id)
            query_part = query_part.outerjoin(self.media_mores[1], self.media_mores[1].media_id == self.media.id)
            search_filter = or_(
                self.media.name.ilike(f"%{self.search}%"),
                self.media_mores[0].name.ilike(f"%{self.search}%"),
                self.media_mores[1].name.ilike(f"%{self.search}%"),
            )
        elif self.media_type == MediaType.BOOKS:
            query_part = query_part.outerjoin(self.media_mores[0], self.media_mores[0].media_id == self.media.id)
            search_filter = or_(
                self.media.name.ilike(f"%{self.search}%"),
                self.media_mores[0].name.ilike(f"%{self.search}%"),
            )
        else:
            return abort(400)

        # Create MAIN SUBQUERY
        paginate_results = (query_part.filter(self.media_list.user_id == self.user.id, search_filter)
                            .group_by(self.media.id).order_by(asc(self.media.name))
                            .paginate(page=int(self.page), per_page=self.PER_PAGE, error_out=True))

        # Add instances attributes
        self.total = paginate_results.total
        self.pages = paginate_results.pages

        # Serialize results
        self.results = [item.to_dict() for item in paginate_results.items]

class ItemsMediaQuery(BaseMediaQuery):
    """ Subclass for handling the display items query part """

    def _items_query(self):
        """ Get the <media_list> items for a specified <user> """

        # Sorting
        sort_filter = self._get_sorting()

        # Status filter
        status_filter = self._get_status_filter()

        # Genre filter
        genre_filter = self.media_genre.genre.like(self.genre) if self.genre != "All" else True

        # Lang filter
        lang_filter = self._get_lang_filter()

        # Show/Hide Common filter
        common_filter = self._get_common_filter()

        # Create MAIN SUBQUERY
        paginate_results = (db.session.query(self.media_list)
                            .outerjoin(self.media, self.media.id == self.media_list.media_id)
                            .outerjoin(self.media_genre, self.media_genre.media_id == self.media.id)
                            .filter(self.media_list.user_id == self.user.id, status_filter, genre_filter, lang_filter,
                                    common_filter)
                            .group_by(self.media.id).order_by(sort_filter, asc(self.media.name))
                            .paginate(page=int(self.page), per_page=self.PER_PAGE, error_out=True))

        # Add instances attributes
        self.total = paginate_results.total
        self.pages = paginate_results.pages

        # Serialize results
        self.results = [item.to_dict() for item in paginate_results.items]

class MediaListQuery(SearchMediaQuery, ItemsMediaQuery):
    """ Main class that handles different query types using inheritance """

    def __init__(self, user: User, media_type: MediaType):
        super().__init__(user, media_type)

    def return_results(self) -> Tuple[Dict, Dict]:
        if self.status == Status.SEARCH:
            self._search_query()
        else:
            self._items_query()

        media_data = dict(
            media_list=self.results,
            total_media=self.total_media,
            common_ids=self.common_ids,
        )

        pagination = dict(
            search=self.search,
            sorting=self.sorting,
            status=self.status,
            genre=self.genre,
            lang=self.lang,
            page=self.page,
            pages=self.pages,
            total=self.total,
            all_status=self.all_status,
            all_genres=self.all_genres,
            all_sorting=list(self.all_sorting.keys()),
        )

        return media_data, pagination
