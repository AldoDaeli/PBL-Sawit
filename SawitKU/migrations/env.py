import logging
from logging.config import fileConfig

from alembic import context
from flask import current_app

config = context.config
fileConfig(config.config_file_name)
logger = logging.getLogger('alembic.env')


def get_engine():
    try:
        return current_app.extensions['migrate'].db.get_engine()      # Flask-SQLAlchemy < 3
    except (TypeError, AttributeError):
        return current_app.extensions['migrate'].db.engine             # Flask-SQLAlchemy >= 3


def get_engine_url():
    try: return get_engine().url.render_as_string(hide_password=False).replace('%', '%%')
    except AttributeError: return str(get_engine().url).replace('%', '%%')


config.set_main_option('sqlalchemy.url', get_engine_url())
target_db = current_app.extensions['migrate'].db


def get_metadata():
    if hasattr(target_db, 'metadatas'): return target_db.metadatas[None]
    return target_db.metadata


def run_migrations_offline():
    context.configure(url=config.get_main_option('sqlalchemy.url'), target_metadata=get_metadata(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    def process_revision_directives(context, revision, directives):      # jangan buat berkas migrasi kosong
        if getattr(config.cmd_opts, 'autogenerate', False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info('Tidak ada perubahan skema.')

    conf_args = current_app.extensions['migrate'].configure_args
    if conf_args.get('process_revision_directives') is None:
        conf_args['process_revision_directives'] = process_revision_directives

    with get_engine().connect() as connection:
        context.configure(connection=connection, target_metadata=get_metadata(), **conf_args)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode(): run_migrations_offline()
else: run_migrations_online()
