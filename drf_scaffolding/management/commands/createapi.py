# -*- coding: utf-8 -*-
import os
import sys

from django.apps import apps
from django.conf import settings as dj_settings
from django.contrib.contenttypes.models import ContentType
from django.core.management import BaseCommand
from django.template import Context, Template

from . import settings, templates


class Command(BaseCommand):
    help = "Starts an api from app models for development."

    can_import_settings = True
    requires_system_checks = False

    def add_arguments(self, parser):
        parser.add_argument(
            'args', metavar='app_label', nargs='*',
            help='Name of the application where you want create the api.',
        )

    def write(self, msg):
        self.stderr.write(msg)

    def join_label_app(self, label, app, is_py_file=True):
        extension = '.py' if is_py_file else ''
        return '{0}/{1}{2}'.format(label, app, extension)

    def file_exists(self, path):
        return os.path.isfile(path)

    def create_file(self, path, context=None, template=None):
        if not self.file_exists(path):
            with open(path, 'w') as f:
                msg = self.join_label_app(
                    'Writing: ', path, is_py_file=False)
                self.write(msg)
                if not context:
                    context = Context()

                if not template:
                    template = ''

                template_loaded = Template(template)
                api_text = template_loaded.render(context)
                f.write(api_text)

    def create_init_file(self, path):
        url = self.join_label_app(path, '__init__')
        self.create_file(url)

    def get_or_create_file(self, path, context=None, template=None):
        if not self.file_exists(path):
            self.create_file(path, context, template)

    def dir_exists(self, path):
        return os.path.isdir(path)

    def create_dir(self, path):
        return os.makedirs(path)

    def get_or_create_dir(self, path):
        if not self.dir_exists(path):
            return self.create_dir(path)
        else:
            return True

    def get_app_labels(self, app_labels):
        exclude_apps = settings.DRF_SETTINGS['exclude_apps']

        if len(app_labels) == 0:
            if hasattr(dj_settings, 'LOCAL_APPS'):
                apps = [i.split('.')[-1] for i in dj_settings.LOCAL_APPS]
            else:
                apps = ContentType.objects.exclude(
                    app_label__in=exclude_apps
                ).values_list(
                    'app_label',
                    flat=True
                ).distinct()

            return set(apps)

        return set(app_labels)

    def write_serializer(self, config_app, model, project_name):
        #
        # create init file into serializers folder
        #
        self.create_init_file(config_app['serializer_path'])

        #
        # Create serializer file
        #
        serializer_path = self.join_label_app(
            config_app['serializer_path'],
            model['name'].lower()
        )

        context = Context({
            'project_name': project_name,
            'app_name': config_app['label'],
            'model': model
        })

        self.get_or_create_file(
            serializer_path,
            context,
            templates.SERIALIZER_TEMPLATE
        )

    def write_api(self, config_app, model, project_name):
        #
        # create init file into viewsets folder
        #
        self.create_init_file(config_app['api_path'])

        #
        # Create api file
        #
        viewset_path = self.join_label_app(
            config_app['api_path'],
            model['name'].lower()
        )

        context = Context({
            'project_name': project_name,
            'app_name': config_app['label'],
            'api_version': config_app['api_version'],
            'model': model
        })

        self.get_or_create_file(viewset_path, context, templates.API_TEMPLATE)

    def write_routes(self, config_app, models, project_name, api_version):
        route_path = self.join_label_app(
            config_app['path'],
            'routes'
        )

        context = Context({
            'models': models,
            'project_name': project_name,
            'api_version': api_version
        })
        #
        # create routes file in app root, for example: polls/routes.py
        #
        self.get_or_create_file(route_path, context, templates.ROUTE_TEMPLATE)

    def get_meta_model_config(self, model):
        if hasattr(model._meta, 'drf_config'):
            if 'api' in model._meta.drf_config:
                api = model._meta.drf_config['api']
                if api['scaffolding'] is True:
                    model_config = {
                        'name': model.__name__,
                    }

                    if 'methods' in api:
                        model_config['methods'] = api['methods']
                    else:
                        model_config['methods'] = [
                            'CREATE',
                            'RETRIEVE',
                            'LIST',
                            'DELETE',
                            'UPDATE'
                        ]

                    if 'serializer' in api:
                        serializer = api['serializer']
                        if 'scaffolding' in serializer:
                            if serializer['scaffolding'] is True:
                                model_config['serializer'] = True
                                if 'fields' in serializer:
                                    model_config['fields'] = serializer['fields']  # noqa
                            else:
                                model_config['serializer'] = False
                        else:
                            model_config['serializer'] = False
                    else:
                        model_config['serializer'] = False

                    return model_config
        return None

    def get_label_app_config(self, app_labels, api_version):
        given_apps_path = []
        bad_app_labels = set()
        for app_label in app_labels:
            try:
                app = apps.get_app_config(app_label)
                models = []
                for m in apps.get_app_config(app_label).get_models():
                    valid_model = self.get_meta_model_config(m)
                    if valid_model:
                        models.append(valid_model)

                given_apps_path.append({
                    'path': app.path,
                    'label': app_label,
                    'api_path': "{0}/viewsets/".format(app.path),
                    'serializer_path': "{0}/serializers/".format(app.path),
                    'models': models,
                    'api_version': api_version,
                    'extra_options': {}
                })
            except LookupError:
                bad_app_labels.add(app_label)

        if bad_app_labels:
            for app_label in bad_app_labels:
                msg = "App '%s' could not be found." % app_label
                self.write(msg)
            sys.exit(2)

        if not given_apps_path:
            self.write("Apps could not be found.")
            sys.exit(2)

        return given_apps_path

    def validate_paths(self, apps_path):
        for app in apps_path:
            api_path = '{0}'.format(app['api_path'])
            serializer_path = '{0}'.format(app['serializer_path'])
            for model in app['models']:
                api_file = self.join_label_app(
                    api_path,
                    model['name'].lower()
                )
                serializer_file = self.join_label_app(
                    serializer_path,
                    model['name'].lower()
                )
                if os.path.isfile(api_file):
                    msg = 'serializer is already exist in app: %s' % app['label']  # noqa
                    self.write(msg)

                if os.path.isfile(serializer_file):
                    msg = 'api is already exist in app: %s' % app['label']
                    self.write(msg)

    def handle(self, *app_labels, **options):
        PROJECT_NAME = dj_settings.BASE_DIR.split('/')[-1]
        API_VERSION = settings.DRF_SETTINGS['version']
        app_labels = self.get_app_labels(app_labels)

        #
        # Make sure the app they asked for exists
        #
        given_apps_path = self.get_label_app_config(app_labels, API_VERSION)

        #
        # Validate applications api path or serializer path exists
        #
        self.validate_paths(given_apps_path)

        for app in given_apps_path:
            self.get_or_create_dir(app['api_path'])
            self.get_or_create_dir(app['serializer_path'])
            for model in app['models']:
                self.write_api(app, model, PROJECT_NAME)
                if model['serializer'] is True:
                    self.write_serializer(app, model, PROJECT_NAME)

            self.write_routes(app, app['models'], PROJECT_NAME, API_VERSION)
