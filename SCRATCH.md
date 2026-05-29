# Scratch / Research Notes

Reference material and links. **API / usage documentation lives in
[API.md](API.md)** — keep this file for research, links, and open questions
only. (Model types, joins, the type system, web-framework error handling, and
the migration system reference now live in [API.md](API.md).)

## sqlite3
https://docs.python.org/3/library/sqlite3.html
https://sqlite.org/np1queryprob.html
https://andre.arko.net/2025/09/11/rails-on-sqlite-exciting-new-ways-to-cause-outages/
https://fractaledmind.com/2024/04/15/sqlite-on-rails-the-how-and-why-of-optimal-performance/
https://rogerbinns.github.io/apsw/cursor.html - Richard Hipp says this is a better wrapper.

## Other big users of apsw
see: https://clickpy.clickhouse.com/dashboard/apsw
- all of these seem to focus on data-exploration / analytics use cases
  - https://github.com/AnswerDotAI/fastlite
  Similar, add CRUD ORM on top of DataClass models that generate straight from the schema, or CREATE from dataclasses.
  - https://sqlite-utils.datasette.io/en/stable/python-api.html / https://github.com/AnswerDotAI/apswutils this is a library and a fork that adds apsw support to sqlite-utils.

## other SQLite ORMs
- https://pypi.org/project/sqler/ (repo seems deleted, downloaded tarball from pypi)


## sqlite extensions
apsw bundles these.
should show example, for instance of turning on and using decimal summation?
