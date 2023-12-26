
# CHANGELOG v1.0.1

## Bug Fixes
- Fixed an issue with user `/search` in navbar: inability to access the other pages.
- Fixed wrong Notifications media name for games.

## Code Refactoring
- Refactored the stats code of the `/medialist` route.
- Refactored the `/profile` route and associated functions for the new tabbed media display.
- Removed the custom SSL SMTP Handler, allowing for TLS only.
- Code refactoring to enhance overall code quality.

## Route Changes
- Merged the `/add_media_to_db` route with the `/details` route for the use of Link instead of onClick in the frontend.

## Error Handling
- Implemented a personalized error message using Flask's abort for the `TMDB API`.

## Structural Changes
- Introduced a `classes` folder for better code organization.

## Security
- Changed cookies settings for the refresh token