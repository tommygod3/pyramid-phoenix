import os
import re
from pyramid.view import view_config, view_defaults
from twitcher.registry import service_registry_factory
from mako.template import Template
import requests
from owslib.wms import WebMapService

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
        self.dataset = self.request.params.get('dataset')
        self.wms = self.get_wms()

    def get_wms(self):
        if not self.dataset:
            return None
        caps_url = self.request.route_url('owsproxy', service_name='wms',
                                          _query=[('dataset', self.dataset),
                                                  ('version', '1.1.1'), ('service', 'WMS'), ('request', 'GetCapabilities')])
        resp = requests.get(caps_url, verify=False)
        return WebMapService(caps_url, xml=resp.content)

    def get_layers(self):
        if len(self.wms.contents) == 1:
            return list(self.wms.contents)[0]
        for layer_id in list(self.wms.contents):
            if layer_id.endswith('/lat') or layer_id.endswith('/lon'):
                continue
            return layer_id
        return None

    def get_available_times(self, layer_id):
        layer = self.wms[layer_id]
        if layer.timepositions:
            return [tpos.strip() for tpos in layer.timepositions]
        return None
        
    @view_config(route_name='map', renderer='templates/map/map.pt')
    def view(self):
        layers = None
        times = None
        if self.dataset:
            layers = self.get_layers()
            timepositions = self.get_available_times(layers)
            if timepositions:
                times = ','.join(timepositions)
        
        text = map_script.render(
            dataset=self.dataset,
            layers=layers,
            styles="default-scalar/x-Rainbow",
            times=times,
            )
        return dict(map_script=text)

def includeme(config):
    settings = config.registry.settings

    logger.info('Adding map ...')

    # views
    config.add_route('map', '/map')

    # configure ncwms
    service_registry = service_registry_factory(config.registry)
    service_registry.register_service(url=settings.get('wms.url'), name='wms', service_type='wms', public=True)



    
