# Tagesschau Article Crawler

This project consists of a web crawler that scrapes all the articles on the overview page of (https://www.tagesschau.de/).


## System parts:

1. Web Crawler: Scrapes article content from Tagesschau.de
2. Version History: Keeps track of changes to articles over time
3. Scheduled Crawling: Automatically crawls for new articles on a configurable schedule
4. REST API: Endpoints for controlling the crawler and exploring the collected data


## To install:

### Prerequisites

- Docker and Docker Compose

### Installation
 - Download/clone the project 
 - Run docker with `docker compose up --build` from the root where `docker-compose.yml` is.
 - The API will be available at: http://localhost:5000. A json collection has been provided for use with Postman.

### Database 

Any database explorer can be used to see the Postgres db. The log in credentials and exposed ports are detailed in 
`docker-compose`

## API Documentation

### Crawler Control
`GET /api/config` - Get current crawler configuration

`PUT /api/config/schedule` - Update schedule interval (JSON payload: {"hours": 2})

`POST /api/config/schedule/increase` - Increase schedule interval by 1 hour

`POST /api/config/schedule/decrease` - Decrease schedule interval by 1 hour

`POST /api/config/enable` - Enable scheduled crawling

`POST /api/config/disable` - Disable scheduled crawling

`POST /api/crawl/overview` - Trigger a full crawl of the overview page

`POST /api/crawl/article` - Crawl a specific article (JSON payload: {"url": "https://www.tagesschau.de/..."})


### Article Exploration
`GET /api/articles` - List all articles (paginated)
- Query parameters: page, per_page

`GET /api/articles/{id}` - Get article details

`GET /api/articles/{id}/versions` - Get all versions of an article

`GET /api/articles/{id}/changes` - Check if an article has changed over time

`GET /api/search - Search articles by keyword`
- Query parameters: q (query), page, per_page

### Examples
#### Trigger a manual crawl
`bashcurl -X POST http://localhost:5000/api/crawl/overview`

#### Change the crawl schedule to every 2 hours
`bashcurl -X PUT http://localhost:5000/api/config/schedule \
  -H "Content-Type: application/json" \
  -d '{"hours": 2}'`

#### Search for articles
`bashcurl -X GET "http://localhost:5000/api/search?q=politik&page=1&per_page=10"`

## Design Decisions
Version History Implementation
- The `articles` table stores the current version of each article, and the `articles_versions` table stores previous versions
When an article changes, the old content is moved to `articles_versions` before updating

Crawler Scheduling
- The scheduler runs in a background thread within the Flask application. Schedule configuration is stored in the database
for persistence and can be adjusted with the API.

Text Search
- Postgres' built-in text search functionality is used for efficient search especially for German language support. Content 
excerpts highlight matches in search results.

There is a third internal API for the crawler,to adhere to separation of concerns. The crawler could at some point need 
more resources for scraping and/or different scaling and this allows for easier updating. Also, if this API fails, the 
other two can still be accessed.
