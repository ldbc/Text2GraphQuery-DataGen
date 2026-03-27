CREATE TABLE `USER` (
  `USER_id`            INT64 NOT NULL,
  `age`                INT64,
  `gender`             STRING(MAX),
  `occupation`         STRING(MAX),
  `zip_code`           STRING(MAX),
  `registration_date`  STRING(MAX)
) PRIMARY KEY (`USER_id`);

CREATE TABLE `MOVIE` (
  `MOVIE_id`           INT64 NOT NULL,
  `title`              STRING(MAX),
  `release_year`       INT64,
  `duration`           INT64,
  `plot_summary`       STRING(MAX),
  `language`           STRING(MAX)
) PRIMARY KEY (`MOVIE_id`);

CREATE TABLE `GENRE` (
  `GENRE_id`           INT64 NOT NULL,
  `name`               STRING(MAX),
  `description`        STRING(MAX)
) PRIMARY KEY (`GENRE_id`);

CREATE TABLE `RATING` (
  `RATING_id`          INT64 NOT NULL,
  `score`              FLOAT64,
  `timestamp`          STRING(MAX),
  `review_text`        STRING(MAX)
) PRIMARY KEY (`RATING_id`);

CREATE TABLE `TAG` (
  `TAG_id`             INT64 NOT NULL,
  `text_content`       STRING(MAX),
  `timestamp`          STRING(MAX),
  `relevance_score`    FLOAT64
) PRIMARY KEY (`TAG_id`);

CREATE TABLE `USERRATESRATING` (
  `SRC_ID`           INT64 NOT NULL,
  `DST_ID`           INT64 NOT NULL,
  `rating_timestamp`   STRING(MAX),
  `rating_value`       FLOAT64,
  `confidence_weight`  FLOAT64,
  FOREIGN KEY (`SRC_ID`) REFERENCES `USER` (`USER_id`),
  FOREIGN KEY (`DST_ID`) REFERENCES `RATING` (`RATING_id`)
) PRIMARY KEY (`SRC_ID`, `DST_ID`, `rating_timestamp`);

CREATE TABLE `RATINGRATESMOVIE` (
  `SRC_ID`           INT64 NOT NULL,
  `DST_ID`           INT64 NOT NULL,
  `rating_timestamp`   STRING(MAX),
  `rating_value`       FLOAT64,
  `confidence_weight`  FLOAT64,
  FOREIGN KEY (`SRC_ID`) REFERENCES `RATING` (`RATING_id`),
  FOREIGN KEY (`DST_ID`) REFERENCES `MOVIE` (`MOVIE_id`)
) PRIMARY KEY (`SRC_ID`, `DST_ID`, `rating_timestamp`);

CREATE TABLE `MOVIEBELONGS_TOGENRE` (
  `SRC_ID`           INT64 NOT NULL,
  `DST_ID`           INT64 NOT NULL,
  `primary_classification` BOOL,
  `strength_score`     FLOAT64,
  FOREIGN KEY (`SRC_ID`) REFERENCES `MOVIE` (`MOVIE_id`),
  FOREIGN KEY (`DST_ID`) REFERENCES `GENRE` (`GENRE_id`)
) PRIMARY KEY (`SRC_ID`, `DST_ID`);

CREATE TABLE `USERTAGSTAG` (
  `SRC_ID`           INT64 NOT NULL,
  `DST_ID`           INT64 NOT NULL,
  `tag_timestamp`      STRING(MAX),
  `user_confidence`    FLOAT64,
  `public_visibility`  BOOL,
  FOREIGN KEY (`SRC_ID`) REFERENCES `USER` (`USER_id`),
  FOREIGN KEY (`DST_ID`) REFERENCES `TAG` (`TAG_id`)
) PRIMARY KEY (`SRC_ID`, `DST_ID`, `tag_timestamp`);

CREATE TABLE `TAGTAGSMOVIE` (
  `SRC_ID`           INT64 NOT NULL,
  `DST_ID`           INT64 NOT NULL,
  `tag_timestamp`      STRING(MAX),
  `user_confidence`    FLOAT64,
  `public_visibility`  BOOL,
  FOREIGN KEY (`SRC_ID`) REFERENCES `TAG` (`TAG_id`),
  FOREIGN KEY (`DST_ID`) REFERENCES `MOVIE` (`MOVIE_id`)
) PRIMARY KEY (`SRC_ID`, `DST_ID`, `tag_timestamp`);

CREATE TABLE `MOVIESIMILAR_TOMOVIE` (
  `SRC_ID`           INT64 NOT NULL,
  `DST_ID`           INT64 NOT NULL,
  `similarity_score`   FLOAT64,
  `algorithm_version`  STRING(MAX),
  `update_timestamp`   STRING(MAX),
  FOREIGN KEY (`SRC_ID`) REFERENCES `MOVIE` (`MOVIE_id`),
  FOREIGN KEY (`DST_ID`) REFERENCES `MOVIE` (`MOVIE_id`)
) PRIMARY KEY (`SRC_ID`, `DST_ID`, `algorithm_version`, `update_timestamp`);

CREATE TABLE `USERFRIENDS_WITHUSER` (
  `SRC_ID`           INT64 NOT NULL,
  `DST_ID`           INT64 NOT NULL,
  `connection_strength` FLOAT64,
  `mutual_interests_count` INT64,
  `last_interaction`   STRING(MAX),
  FOREIGN KEY (`SRC_ID`) REFERENCES `USER` (`USER_id`),
  FOREIGN KEY (`DST_ID`) REFERENCES `USER` (`USER_id`)
) PRIMARY KEY (`SRC_ID`, `DST_ID`, `mutual_interests_count`, `last_interaction`);

CREATE OR REPLACE PROPERTY GRAPH `generated_schemas`
  NODE TABLES (`GENRE`, `MOVIE`, `RATING`, `TAG`, `USER`)
  EDGE TABLES (
    `USERRATESRATING`
      KEY (`SRC_ID`, `DST_ID`, `rating_timestamp`)
      SOURCE KEY (`SRC_ID`) REFERENCES `USER` (`USER_id`)
      DESTINATION KEY (`DST_ID`) REFERENCES `RATING` (`RATING_id`)
      LABEL `RATES`,
    `RATINGRATESMOVIE`
      KEY (`SRC_ID`, `DST_ID`, `rating_timestamp`)
      SOURCE KEY (`SRC_ID`) REFERENCES `RATING` (`RATING_id`)
      DESTINATION KEY (`DST_ID`) REFERENCES `MOVIE` (`MOVIE_id`)
      LABEL `RATES`,
    `MOVIEBELONGS_TOGENRE`
      KEY (`SRC_ID`, `DST_ID`)
      SOURCE KEY (`SRC_ID`) REFERENCES `MOVIE` (`MOVIE_id`)
      DESTINATION KEY (`DST_ID`) REFERENCES `GENRE` (`GENRE_id`)
      LABEL `BELONGS_TO`,
    `USERTAGSTAG`
      KEY (`SRC_ID`, `DST_ID`, `tag_timestamp`)
      SOURCE KEY (`SRC_ID`) REFERENCES `USER` (`USER_id`)
      DESTINATION KEY (`DST_ID`) REFERENCES `TAG` (`TAG_id`)
      LABEL `TAGS`,
    `TAGTAGSMOVIE`
      KEY (`SRC_ID`, `DST_ID`, `tag_timestamp`)
      SOURCE KEY (`SRC_ID`) REFERENCES `TAG` (`TAG_id`)
      DESTINATION KEY (`DST_ID`) REFERENCES `MOVIE` (`MOVIE_id`)
      LABEL `TAGS`,
    `MOVIESIMILAR_TOMOVIE`
      KEY (`SRC_ID`, `DST_ID`, `algorithm_version`, `update_timestamp`)
      SOURCE KEY (`SRC_ID`) REFERENCES `MOVIE` (`MOVIE_id`)
      DESTINATION KEY (`DST_ID`) REFERENCES `MOVIE` (`MOVIE_id`)
      LABEL `SIMILAR_TO`,
    `USERFRIENDS_WITHUSER`
      KEY (`SRC_ID`, `DST_ID`, `mutual_interests_count`, `last_interaction`)
      SOURCE KEY (`SRC_ID`) REFERENCES `USER` (`USER_id`)
      DESTINATION KEY (`DST_ID`) REFERENCES `USER` (`USER_id`)
      LABEL `FRIENDS_WITH`
  );