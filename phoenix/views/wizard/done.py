from pyramid.view import view_config
import json

from phoenix.views.wizard import Wizard

import logging
logger = logging.getLogger(__name__)

class Done(Wizard):
    def __init__(self, request):
        super(Done, self).__init__(
            request, name='wizard_done', title="Done")
        self.description = "Describe your Job and start Workflow."
        from owslib.wps import WebProcessingService
        self.wps = WebProcessingService(self.wizard_state.get('wizard_wps')['url'])
        self.csw = self.request.csw

    def breadcrumbs(self):
        breadcrumbs = super(Done, self).breadcrumbs()
        breadcrumbs.append(dict(route_path=self.request.route_path(self.name), title=self.title))
        return breadcrumbs

    def schema(self):
        from phoenix.schema import DoneSchema
        return DoneSchema()

    def workflow_description(self, name):
        nodes = {}

        user = self.get_user()
        if 'swift' in name:
            source = dict(
                service = self.request.wps.url,
                storage_url = user.get('swift_storage_url'),
                auth_token = user.get('swift_auth_token'),
            )
            source['container'] = self.wizard_state.get('wizard_swiftbrowser')['container']
            source['prefix'] = self.wizard_state.get('wizard_swiftbrowser')['prefix']
            nodes['source'] = source
            logger.debug('source = %s', source)
        else: # esgsearch
            credentials = user.get('credentials')

            selection = self.wizard_state.get('wizard_esgf_search')['selection']
            esgsearch = json.loads(selection)
            nodes['esgsearch'] = esgsearch
            
            source = dict(
                service = self.request.wps.url,
                credentials=credentials,
            )
            nodes['source'] = source

        from phoenix.utils import appstruct_to_inputs
        inputs = appstruct_to_inputs(self.wizard_state.get('wizard_literal_inputs', {}))
        worker_inputs = ['%s=%s' % (key, value) for key,value in inputs]
        worker = dict(
            service = self.wps.url,
            identifier = self.wizard_state.get('wizard_process')['identifier'],
            inputs = [(key, value) for key,value in inputs],
            resource = self.wizard_state.get('wizard_complex_inputs')['identifier'],
            )
        nodes['worker'] = worker
        return nodes

    def execute_workflow(self, appstruct):
        source = self.wizard_state.get('wizard_source')['source']
        if 'swift' in source:
            name = 'swift_workflow'
        else:
            name = 'esgsearch_workflow'
        nodes = self.workflow_description(name)
        nodes_json = json.dumps(nodes)

        # generate and run dispel workflow
        identifier='dispel'
        inputs=[('nodes', nodes_json), ('name', name)]
        outputs=[('output', True)]
        from phoenix.tasks import execute
        execute.delay(self.user_email(), self.request.wps.url, identifier, 
                      inputs=inputs, outputs=outputs, workflow=True)

    def success(self, appstruct):
        super(Done, self).success(appstruct)
        if appstruct.get('is_favorite', False):
            self.favorite.set(
                name=appstruct.get('favorite_name'),
                state=self.wizard_state.dump())
            self.favorite.save()
        
        execution = self.execute_workflow(appstruct)
        
    def next_success(self, appstruct):
        from pyramid.httpexceptions import HTTPFound
        self.success(appstruct)
        self.wizard_state.clear()
        return HTTPFound(location=self.request.route_url('myjobs'))

    def appstruct(self):
        appstruct = super(Done, self).appstruct()
        #params = ', '.join(['%s=%s' % item for item in self.wizard_state.get('wizard_literal_inputs', {}).items()])
        identifier = self.wizard_state.get('wizard_process')['identifier']
        appstruct.update( dict(favorite_name=identifier) )
        return appstruct

    @view_config(route_name='wizard_done', renderer='phoenix:templates/wizard/default.pt')
    def view(self):
        return super(Done, self).view()
