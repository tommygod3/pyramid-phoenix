from pyramid.view import view_config

from phoenix.wizard.views import Wizard
from phoenix.catalog import wps_url

import colander
import deform

choices = [
    ('wizard_esgf_search', "Earth System Grid (ESGF)"),
    ('wizard_swift_login', "Swift Cloud"),
    ('wizard_threddsservice', "Thredds Catalog Service")]

import logging
logger = logging.getLogger(__name__)
    
class ChooseSource(Wizard):
    def __init__(self, request):
        super(ChooseSource, self).__init__(
            request, name='wizard_source', title="Choose Data Source")
        from owslib.wps import WebProcessingService
        self.wps = WebProcessingService(wps_url(request, self.wizard_state.get('wizard_wps')['identifier']))
        self.process = self.wps.describeprocess(self.wizard_state.get('wizard_process')['identifier'])

    def breadcrumbs(self):
        breadcrumbs = super(ChooseSource, self).breadcrumbs()
        breadcrumbs.append(dict(route_path=self.request.route_path(self.name), title=self.title))
        return breadcrumbs
        
    def schema(self):
        schema = colander.SchemaNode(colander.Mapping())
        
        for data_input in self.process.dataInputs:
            if data_input.dataType != 'ComplexData':
                continue
            mime_types = ', '.join([value.mimeType for value in data_input.supportedValues])
        
            source = colander.SchemaNode(
                colander.String(),
                name = data_input.identifier,
                title = data_input.title,
                description = getattr(data_input, 'abstract'),
                widget = deform.widget.RadioChoiceWidget(values=choices))
        
            schema.add(source)
        return schema

    def next_success(self, appstruct):
        self.success(appstruct)
        logger.debug(appstruct)
        return self.next( appstruct.items()[0][1] )
        
    @view_config(route_name='wizard_source', renderer='../templates/wizard/default.pt')
    def view(self):
        return super(ChooseSource, self).view()
    
