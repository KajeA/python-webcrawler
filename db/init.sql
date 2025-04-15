-- For setting up the db

-- articles table
CREATE TABLE articles (
    id SERIAL PRIMARY KEY,
    url VARCHAR(255) NOT NULL UNIQUE,
    headline VARCHAR(255) NOT NULL,
    sub_headline VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    updated_at TIMESTAMP,
    first_crawled_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_crawled_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- articles_versions table to hold previous versions of articles
CREATE TABLE articles_versions (
    id SERIAL PRIMARY KEY,
    article_id INT REFERENCES articles(id) ON DELETE CASCADE,
    headline VARCHAR(255) NOT NULL,
    sub_headline VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    crawled_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- crawler_config table to hold crawler configuration
CREATE TABLE crawler_config (
    id INT PRIMARY KEY DEFAULT 1, -- only one record needed
    schedule_interval_hours INT NOT NULL DEFAULT 1,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    last_run TIMESTAMP,
    next_run TIMESTAMP
);

-- insert default config
INSERT INTO crawler_config (schedule_interval_hours, is_enabled)
VALUES (1, TRUE);

-- create index for text search on articles table using Generic Inverted Index (GIN) adjusted for Deutsch
CREATE INDEX idx_articles_headline ON articles USING gin(to_tsvector('german', headline));
CREATE INDEX idx_articles_content ON articles USING gin(to_tsvector('german', content));
