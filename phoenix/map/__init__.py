import os
import requests

from pyramid.view import view_config, view_defaults
from pyramid.settings import asbool
from pyramid.events import NewRequest
from mako.template import Template
from owslib.wms import WebMapService

from twitcher.registry import service_registry_factory

import logging
logger = logging.getLogger(__name__)

map_script = Template(
    filename=os.path.join(os.path.dirname(__file__), "templates", "map", "map.js"),
    output_encoding="utf-8", input_encoding="utf-8")


@view_defaults(permission='view', layout='default')
class Map(object):
    def __init__(self, request):
        self.request = request
        self.session = self.request.session

    def view(self):
        dataset = self.request.params.get('dataset')
        wms_url = self.request.params.get('wms_url')
        if dataset:
            use_proxy = False
            url = self.request.route_url(
                'owsproxy',
                service_name='wms',
                _query=[('DATASET', dataset)])
            caps_url = self.request.route_url(
                'owsproxy',
                service_name='wms',
                _query=[('DATASET', dataset),
                        ('service', 'WMS'), ('request', 'GetCapabilities'), ('version', '1.1.1')])
            try:
                response = requests.get(caps_url, verify=False)
                if not response.ok:
                    raise Exception("get caps failed: url=%s", caps_url)
                wms = WebMapService(url, version='1.1.1', xml=response.content)
                map_name = dataset.split('/')[-1]
            except:
                logger.exception("wms connect failed")
                raise Exception("could not connect to wms url %s", caps_url)
        elif wms_url:
            use_proxy = True
            try:
                wms = WebMapService(wms_url)
                map_name = wms_url.split('/')[-1]
            except:
                logger.exception("wms connect failed")
                raise Exception("could not connet to wms url %s", wms_url)
        else:
            wms = None
            map_name = None
            use_proxy = False
        return dict(map_script=map_script.render(wms=wms, dataset=dataset, use_proxy=use_proxy),
                    map_name=map_name)


def includeme(config):
    settings = config.registry.settings

    def wms_activated(request):
        return asbool(settings.get('phoenix.wms', 'false'))
    config.add_request_method(wms_activated, reify=True)

    def wms_url(request):
        return settings.get('wms.url')
    config.add_request_method(wms_url, reify=True)

    if asbool(settings.get('phoenix.wms', 'false')):
        # add wms service
        def add_wms(event):
            request = event.request
            # settings = event.request.registry.settings
            if request.wms_activated and not 'wms' in settings:
                logger.debug('register wms service')
                try:
                    service_name = 'wms'
                    registry = service_registry_factory(request.registry)
                    logger.debug("register: name=%s, url=%s", service_name, settings['wms.url'])
                    registry.register_service(name=service_name, url=settings['wms.url'],
                                              public=True, service_type='wms',
                                              overwrite=True)
                    settings['wms'] = WebMapService(url=settings['wms.url'])
                except:
                    logger.exception('Could not connect wms %s', settings['wms.url'])
            event.request.wms = settings.get('wms')
        config.add_subscriber(add_wms, NewRequest)

        # map view
        config.add_route('map', '/map')
        config.add_view('phoenix.map.Map',
                        route_name='map',
                        attr='view',
                        renderer='templates/map/map.pt')
