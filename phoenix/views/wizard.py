from pyramid.view import view_config, view_defaults
from pyramid.httpexceptions import HTTPFound

from deform import Form, Button

from owslib.wps import WebProcessingService

from string import Template

from phoenix import models
from phoenix.views import MyView
from phoenix.grid import MyGrid
from phoenix.exceptions import MyProxyLogonFailure

import logging
logger = logging.getLogger(__name__)

class WizardFavorite(object):
    session_name = "wizard_favorite"
    
    def __init__(self, session):
        self.session = session
        if not self.session_name in self.session:
            self.clear()
            
    def get(self, key, default=None):
        return self.session[self.session_name].get(key)

    def names(self):
        return self.session[self.session_name].keys()

    def set(self, key, value):
        self.session[self.session_name][key] = value
        self.session.changed()
        
    def clear(self):
        self.session[self.session_name] = {'No Favorite': {},}
        self.session.changed()

class WizardState(object):
    def __init__(self, session, initial_step='wizard', final_step='wizard_done'):
        self.session = session
        self.initial_step = initial_step
        self.final_step = final_step
        if not 'wizard' in self.session:
            self.clear()

    def load(self, state):
        self.clear()
        #self.session['wizard'] = state
        self.session.changed()
            
    def current_step(self):
        step = self.initial_step
        if len(self.session['wizard']['chain']) > 0:
            step = self.session['wizard']['chain'][-1]
        return step

    def is_first(self):
        return self.current_step() == self.initial_step

    def is_last(self):
        return self.current_step() == self.final_step

    def next(self, step):
        self.session['wizard']['chain'].append(step)
        self.session.changed()

    def previous(self):
        if len(self.session['wizard']['chain']) > 1:
            self.session['wizard']['chain'].pop()
            self.session.changed()

    def get(self, key, default=None):
        if self.session['wizard']['state'].get(key) is None:
            self.session['wizard']['state'][key] = default
            self.session.changed()
        return self.session['wizard']['state'].get(key)

    def set(self, key, value):
        self.session['wizard']['state'][key] = value
        self.session.changed()

    def clear(self):
        self.session['wizard'] = dict(state={}, chain=[self.initial_step])
        self.session.changed()

@view_defaults(permission='view', layout='default')
class Wizard(MyView):
    def __init__(self, request, title, description=None, readonly=False):
        super(Wizard, self).__init__(request, title, description)
        self.csw = self.request.csw
        self.wizard_state = WizardState(self.session)
        self.favorite = WizardFavorite(self.session)
        self.readonly = readonly
        
    def buttons(self):
        prev_disabled = not self.prev_ok()
        next_disabled = not self.next_ok()

        prev_button = Button(name='previous', title='Previous',
                             disabled=prev_disabled)   #type=submit|reset|button,value=name,css_type="btn-..."
        next_button = Button(name='next', title='Next',
                             disabled=next_disabled)
        done_button = Button(name='next', title='Done',
                             disabled=next_disabled)
        cancel_button = Button(name='cancel', title='Cancel',
                               css_class='btn btn-danger',
                               disabled=False)
        buttons = []
        # TODO: fix focus button
        if not self.wizard_state.is_first():
            buttons.append(prev_button)
        if self.wizard_state.is_last():
            buttons.append(done_button)
        else:
            buttons.append(next_button)
        buttons.append(cancel_button)
        return buttons

    def prev_ok(self):
        return True

    def next_ok(self):
        return True
    
    def use_ajax(self):
        return False

    def ajax_options(self):
        options = """
        {success:
           function (rText, sText, xhr, form) {
             deform.processCallbacks();
             deform.focusFirstInput();
             var loc = xhr.getResponseHeader('X-Relocate');
                if (loc) {
                  document.location = loc;
                };
             }
        }
        """
        return options

    def appstruct(self):
        return {}

    def schema(self):
        raise NotImplementedError

    def previous_success(self, appstruct):
        raise NotImplementedError
    
    def next_success(self, appstruct):
        raise NotImplementedError

    def generate_form(self, formid='deform'):
        return Form(
            schema = self.schema(),
            buttons=self.buttons(),
            formid=formid,
            use_ajax=self.use_ajax(),
            ajax_options=self.ajax_options(),
            )

    def process_form(self, form, action):
        from deform import ValidationFailure
        
        success_method = getattr(self, '%s_success' % action)
        try:
            controls = self.request.POST.items()
            appstruct = form.validate(controls)
            result = success_method(appstruct)
        except ValidationFailure as e:
            logger.exception('Validation of wizard view failed.')
            result = dict(form=e.render())
        return result
        
    def previous(self):
        self.wizard_state.previous()
        return HTTPFound(location=self.request.route_url(self.wizard_state.current_step()))

    def next(self, step):
        self.wizard_state.next(step)
        return HTTPFound(location=self.request.route_url(self.wizard_state.current_step()))

    def cancel(self):
        self.wizard_state.clear()
        return HTTPFound(location=self.request.route_url(self.wizard_state.current_step()))

    def custom_view(self):
        return {}

    def breadcrumbs(self):
        breadcrumbs = super(Wizard, self).breadcrumbs()
        breadcrumbs.append(dict(route_name='wizard_wps', title="Wizard"))
        return breadcrumbs

    def view(self):
        form = self.generate_form()
        
        if 'previous' in self.request.POST:
            return self.process_form(form, 'previous')
        elif 'next' in self.request.POST:
            return self.process_form(form, 'next')
        elif 'cancel' in self.request.POST:
            return self.cancel()
        
        custom = self.custom_view()    
        result = dict(form=form.render(self.appstruct(), readonly=self.readonly))

        # custom overwrites result
        return dict(result, **custom)

class StartWizard(Wizard):
    def __init__(self, request):
        super(StartWizard, self).__init__(request, 'Wizard')
        self.description = "Choose Favorite or None."
        self.wizard_state.clear()

    def schema(self):
        from phoenix.schema import WizardSchema
        return WizardSchema().bind(favorites=self.favorite.names())

    def success(self, appstruct):
        favorite_state = self.favorite.get(appstruct.get('favorite', 'None'))
        self.wizard_state.load(favorite_state)
        self.wizard_state.set('wizard', appstruct)

    def previous_success(self, appstruct):
        self.success(appstruct)
        return self.previous()

    def next_success(self, appstruct):
        self.success(appstruct)
        return self.next('wizard_wps')

    def appstruct(self):
        return self.wizard_state.get('wizard', {})

    @view_config(route_name='wizard', renderer='phoenix:templates/wizard/default.pt')
    def view(self):
        return super(StartWizard, self).view()

class ChooseWPS(Wizard):
    def __init__(self, request):
        super(ChooseWPS, self).__init__(request, 'WPS')
        self.description = "Choose Web Processing Service"

    def schema(self):
        from phoenix.schema import ChooseWPSSchema
        return ChooseWPSSchema().bind(wps_list = models.get_wps_list(self.request))

    def success(self, appstruct):
        self.wizard_state.set('wps_url', appstruct.get('url'))

    def previous_success(self, appstruct):
        self.success(appstruct)
        return self.previous()

    def next_success(self, appstruct):
        self.success(appstruct)
        return self.next('wizard_process')

    def appstruct(self):
        return dict(url=self.wizard_state.get('wps_url'))

    @view_config(route_name='wizard_wps', renderer='phoenix:templates/wizard/default.pt')
    def view(self):
        return super(ChooseWPS, self).view()

class ChooseWPSProcess(Wizard):
    def __init__(self, request):
        super(ChooseWPSProcess, self).__init__(request, 'Choose WPS Process')
        self.wps = WebProcessingService(self.wizard_state.get('wps_url'))
        self.description = self.wps.identification.title

    def schema(self):
        from phoenix.schema import SelectProcessSchema
        return SelectProcessSchema().bind(processes = self.wps.processes)

    def success(self, appstruct):
        self.wizard_state.set('process_identifier', appstruct.get('identifier'))

    def previous_success(self, appstruct):
        self.success(appstruct)
        return self.previous()
        
    def next_success(self, appstruct):
        self.success(appstruct)
        return self.next('wizard_literal_inputs')
        
    def appstruct(self):
        return dict(identifier=self.wizard_state.get('process_identifier'))

    def breadcrumbs(self):
        breadcrumbs = super(ChooseWPSProcess, self).breadcrumbs()
        breadcrumbs.append(dict(route_name='wizard_literal_inputs', title=self.title))
        return breadcrumbs

    @view_config(route_name='wizard_process', renderer='phoenix:templates/wizard/default.pt')
    def view(self):
        return super(ChooseWPSProcess, self).view()

class LiteralInputs(Wizard):
    def __init__(self, request):
        super(LiteralInputs, self).__init__(
            request,
            "Literal Inputs",
            "")
        self.wps = WebProcessingService(self.wizard_state.get('wps_url'))
        self.process = self.wps.describeprocess(self.wizard_state.get('process_identifier'))
        self.description = "Process %s" % self.process.title

    def schema(self):
        from phoenix.wps import WPSSchema
        return WPSSchema(info=False, hide_complex=True, process = self.process)

    def success(self, appstruct):
        self.wizard_state.set('literal_inputs', appstruct)

    def previous_success(self, appstruct):
        self.success(appstruct)
        return self.previous()
    
    def next_success(self, appstruct):
        self.success(appstruct)
        return self.next('wizard_complex_inputs')
    
    def appstruct(self):
        return self.wizard_state.get('literal_inputs', {})

    def breadcrumbs(self):
        breadcrumbs = super(LiteralInputs, self).breadcrumbs()
        breadcrumbs.append(dict(route_name='wizard_literal_inputs', title=self.title))
        return breadcrumbs

    @view_config(route_name='wizard_literal_inputs', renderer='phoenix:templates/wizard/default.pt')
    def view(self):
        return super(LiteralInputs, self).view()

class ComplexInputs(Wizard):
    def __init__(self, request):
        super(ComplexInputs, self).__init__(
            request,
            "Choose Complex Input Parameter",
            "")
        self.wps = WebProcessingService(self.wizard_state.get('wps_url'))
        self.process = self.wps.describeprocess(self.wizard_state.get('process_identifier'))
        self.description = "Process %s" % self.process.title

    def schema(self):
        from phoenix.schema import ChooseInputParamterSchema
        return ChooseInputParamterSchema().bind(process=self.process)

    def success(self, appstruct):
        self.wizard_state.set('complex_input_identifier', appstruct.get('identifier'))
        for input in self.process.dataInputs:
            if input.identifier == appstruct.get('identifier'):
                self.wizard_state.set('mime_types', [value.mimeType for value in input.supportedValues])

    def previous_success(self, appstruct):
        self.success(appstruct)
        return self.previous()

    def next_success(self, appstruct):
        self.success(appstruct)
        return self.next('wizard_source')

    def appstruct(self):
        return dict(identifier=self.wizard_state.get('complex_input_identifier'))

    def breadcrumbs(self):
        breadcrumbs = super(ComplexInputs, self).breadcrumbs()
        breadcrumbs.append(dict(route_name='wizard_complex_inputs', title=self.title))
        return breadcrumbs

    @view_config(route_name='wizard_complex_inputs', renderer='phoenix:templates/wizard/default.pt')
    def view(self):
        return super(ComplexInputs, self).view()

class ChooseSource(Wizard):
    def __init__(self, request):
        super(ChooseSource, self).__init__(
            request,
            "Choose Source",
            "")
        self.description = self.wizard_state.get('complex_input_identifier')
    def schema(self):
        from phoenix.schema import ChooseSourceSchema
        return ChooseSourceSchema()

    def success(self, appstruct):
        self.wizard_state.set('source', appstruct.get('source'))

    def previous_success(self, appstruct):
        self.success(appstruct)
        return self.previous()

    def next_success(self, appstruct):
        self.success(appstruct)
        return self.next( self.wizard_state.get('source') )
        
    def appstruct(self):
        return dict(source=self.wizard_state.get('source'))

    def breadcrumbs(self):
        breadcrumbs = super(ChooseSource, self).breadcrumbs()
        breadcrumbs.append(dict(route_name='wizard_source', title=self.title))
        return breadcrumbs

    @view_config(route_name='wizard_source', renderer='phoenix:templates/wizard/default.pt')
    def view(self):
        return super(ChooseSource, self).view()
    
class CatalogSearch(Wizard):
    def __init__(self, request):
        super(CatalogSearch, self).__init__(
            request,
            "CSW Catalog Search")
        self.description = self.wizard_state.get('complex_input_identifier')

    def schema(self):
        from phoenix.schema import CatalogSearchSchema
        return CatalogSearchSchema()

    def success(self, appstruct):
        #self.wizard_state.set('esgf_files', appstruct.get('url'))
        pass

    def previous_success(self, appstruct):
        self.success(appstruct)
        return self.previous()

    def next_success(self, appstruct):
        self.success(appstruct)
        return self.next('wizard_check_parameters')

    def search_csw(self, query=''):
        keywords = [k for k in map(str.strip, str(query).split(' ')) if len(k)>0]

        # TODO: search all formats
        format = self.wizard_state.get('mime_types')[0]

        cql_tmpl = Template("""\
        dc:creator='${email}'\
        and dc:format='${format}'
        """)
        cql = cql_tmpl.substitute({
            'email': self.get_user().get('email'),
            'format': format})
        cql_keyword_tmpl = Template('and csw:AnyText like "%${keyword}%"')
        for keyword in keywords:
            cql += cql_keyword_tmpl.substitute({'keyword': keyword})

        results = []
        try:
            self.csw.getrecords(esn="full", cql=cql)
            logger.debug('csw results %s', self.csw.results)
            for rec in self.csw.records:
                myrec = self.csw.records[rec]
                results.append(dict(
                    source = myrec.source,
                    identifier = myrec.identifier,
                    title = myrec.title,
                    abstract = myrec.abstract,
                    subjects = myrec.subjects,
                    format = myrec.format,
                    creator = myrec.creator,
                    modified = myrec.modified,
                    bbox = myrec.bbox,
                    references = myrec.references,
                    ))
        except:
            logger.exception('could not get items for csw.')
        return results
        
    @view_config(renderer='json', name='select.csw')
    def select_csw(self):
        # TODO: refactor this ... not efficient
        identifier = self.request.params.get('identifier', None)
        logger.debug('called with %s', identifier)
        if identifier is not None:
            selection = self.wizard_state.get('csw_selection', [])
            if identifier in selection:
                selection.remove(identifier)
            else:
                selection.append(identifier)
            self.wizard_state.set('csw_selection', selection)
        return {}

    def appstruct(self):
        return dict(csw_selection=self.wizard_state.get('csw_selection'))

    def custom_view(self):
        query = self.request.params.get('query', None)
        checkbox = self.request.params.get('checkbox', None)
        items = self.search_csw(query)
        for item in items:            
            if item['identifier'] in self.wizard_state.get('csw_selection', []):
                item['selected'] = True
            else:
                item['selected'] = False

        grid = CatalogSearchGrid(
                self.request,
                items,
                ['title', 'format', 'selected'],
            )
        return dict(grid=grid, items=items)

    def breadcrumbs(self):
        breadcrumbs = super(CatalogSearch, self).breadcrumbs()
        breadcrumbs.append(dict(route_name='wizard_csw', title=self.title))
        return breadcrumbs

    @view_config(route_name='wizard_csw', renderer='phoenix:templates/wizard/csw.pt')
    def view(self):
        return super(CatalogSearch, self).view()

class CatalogSearchGrid(MyGrid):
    def __init__(self, request, *args, **kwargs):
        super(CatalogSearchGrid, self).__init__(request, *args, **kwargs)
        self.column_formats['selected'] = self.selected_td
        self.column_formats['title'] = self.title_td
        self.column_formats['format'] = self.format_td
        self.column_formats['modified'] = self.modified_td

    def title_td(self, col_num, i, item):
        return self.render_title_td(item['title'], item['abstract'], item.get('subjects'))

    def format_td(self, col_num, i, item):
        return self.render_format_td(item['format'], item['source'])

    def modified_td(self, col_num, i, item):
        return self.render_timestamp_td(timestamp=item.get('modified'))

    def selected_td(self, col_num, i, item):
        from string import Template
        from webhelpers.html.builder import HTML

        icon_class = "icon-thumbs-down"
        if item['selected'] == True:
            icon_class = "icon-thumbs-up"
        div = Template("""\
        <button class="btn btn-mini select" data-value="${identifier}"><i class="${icon_class}"></i></button>
        """)
        return HTML.td(HTML.literal(div.substitute({'identifier': item['identifier'], 'icon_class': icon_class} )))

class ESGFSearch(Wizard):
    def __init__(self, request):
        super(ESGFSearch, self).__init__(
            request,
            "ESGF Search",
            "")

    def schema(self):
        from phoenix.schema import ESGFSearchSchema
        return ESGFSearchSchema()

    def success(self, appstruct):
        self.wizard_state.set('esgf_selection', appstruct.get('selection'))

    def previous_success(self, appstruct):
        self.success(appstruct)
        return self.previous()
        
    def next_success(self, appstruct):
        self.success(appstruct)
        return self.next('wizard_esgf_files')

    def appstruct(self):
        return dict(selection=self.wizard_state.get('esgf_selection', {}))

    def breadcrumbs(self):
        breadcrumbs = super(ESGFSearch, self).breadcrumbs()
        breadcrumbs.append(dict(route_name='wizard_esgf', title=self.title))
        return breadcrumbs

    @view_config(route_name='wizard_esgf', renderer='phoenix:templates/wizard/esgf.pt')
    def view(self):
        return super(ESGFSearch, self).view()

class ESGFFileSearch(Wizard):
    def __init__(self, request):
        super(ESGFFileSearch, self).__init__(
            request,
            "ESGF File Search",
            "")

    def schema(self):
        from phoenix.schema import ESGFFilesSchema
        return ESGFFilesSchema().bind(selection=self.wizard_state.get('esgf_selection'))

    def success(self, appstruct):
        self.wizard_state.set('esgf_files', appstruct.get('url'))

    def previous_success(self, appstruct):
        self.success(appstruct)
        return self.previous()
        
    def next_success(self, appstruct):
        self.success(appstruct)
        return self.next('wizard_esgf_credentials')
        
    def appstruct(self):
        return dict(url=self.wizard_state.get('esgf_files'))

    def breadcrumbs(self):
        breadcrumbs = super(ESGFFileSearch, self).breadcrumbs()
        breadcrumbs.append(dict(route_name='wizard_esgf_files', title=self.title))
        return breadcrumbs

    @view_config(route_name='wizard_esgf_files', renderer='phoenix:templates/wizard/esgf.pt')
    def view(self):
        return super(ESGFFileSearch, self).view()

class ESGFCredentials(Wizard):
    def __init__(self, request):
        super(ESGFCredentials, self).__init__(
            request,
            "ESGF Credentials",
            "")

    def schema(self):
        from phoenix.schema import CredentialsSchema
        return CredentialsSchema().bind()

    def success(self, appstruct):
        try:
            self.wizard_state.set('password', appstruct.get('password'))
            result = models.myproxy_logon(
                self.request,
                openid=self.get_user().get('openid'),
                password=appstruct.get('password'))
            user = self.get_user()
            user['credentials'] = result['credentials']
            user['cert_expires'] = result['cert_expires'] 
            self.userdb.update({'email':self.user_email()}, user)
        except Exception, e:
            logger.exception("update credentials failed.")
            self.request.session.flash(
                "Could not update your credentials. %s" % (e), queue='error')
        else:
            self.request.session.flash(
                'Credentials updated.', queue='success')
        
    def previous_success(self, appstruct):
        self.success(appstruct)
        return self.previous()
        
    def next_success(self, appstruct):
        self.success(appstruct)
        return self.next('wizard_check_parameters')
        
    def appstruct(self):
        return dict(
            openid=self.get_user().get('openid'),
            password=self.wizard_state.get('password'))

    def breadcrumbs(self):
        breadcrumbs = super(ESGFCredentials, self).breadcrumbs()
        breadcrumbs.append(dict(route_name='wizard_esgf_credentials', title=self.title))
        return breadcrumbs

    @view_config(route_name='wizard_esgf_credentials', renderer='phoenix:templates/wizard/esgf.pt')
    def view(self):
        return super(ESGFCredentials, self).view()

class CheckParameters(Wizard):
    def __init__(self, request):
        super(CheckParameters, self).__init__(
            request,
            "Check Parameters",
            "",
            readonly=False)
        self.wps = WebProcessingService(self.wizard_state.get('wps_url'))
        self.process = self.wps.describeprocess(self.wizard_state.get('process_identifier'))
        self.description = "Process %s" % self.process.title

    def schema(self):
        #from phoenix.wps import WPSSchema
        #return WPSSchema(info=False, hide_complex=False, process = self.process)
        from phoenix.schema import NoSchema
        return NoSchema()

    def success(self, appstruct):
        pass

    def previous_success(self, appstruct):
        return self.previous()
        
    def next_success(self, appstruct):
        return self.next('wizard_done')
        
    def appstruct(self):
        return dict(identifier=self.wizard_state.get('complex_input_identifier'))

    def breadcrumbs(self):
        breadcrumbs = super(CheckParameters, self).breadcrumbs()
        breadcrumbs.append(dict(route_name='wizard_check_parameters', title=self.title))
        return breadcrumbs

    @view_config(route_name='wizard_check_parameters', renderer='phoenix:templates/wizard/default.pt')
    def view(self):
        return super(CheckParameters, self).view()

class Done(Wizard):
    def __init__(self, request):
        super(Done, self).__init__(
            request,
            "Done",
            "Describe your Job and start Workflow.")
        self.wps = WebProcessingService(self.wizard_state.get('wps_url'))
        self.csw = self.request.csw

    def schema(self):
        from phoenix.schema import DoneSchema
        return DoneSchema().bind(
            title=self.wizard_state.get('process_identifier'),
            abstract=self.wizard_state.get('literal_inputs'),
            keywords="test",
            favorite_name=self.wizard_state.get('process_identifier'))

    def sources(self):
        sources = []
        source = self.wizard_state.get('source')
        if source == 'wizard_csw':
            self.csw.getrecordbyid(id=self.wizard_state.get('csw_selection', []))
            sources = [[str(rec.source)] for rec in self.csw.records.values()]
        elif source == 'wizard_esgf':
            sources = [[str(file_url)] for file_url in self.wizard_state.get('esgf_files')]
        return sources

    def workflow_description(self):
        credentials = self.get_user().get('credentials')

        source = dict(
            service = self.request.wps.url,
            identifier = 'esgf_wget',
            input = ['credentials=%s' % (credentials)],
            complex_input = 'source',
            output = ['output'],
            sources = self.sources())
        from phoenix.wps import appstruct_to_inputs
        inputs = appstruct_to_inputs(self.wizard_state.get('literal_inputs'))
        worker_inputs = ['%s=%s' % (key, value) for key,value in inputs]
        worker = dict(
            service = self.wps.url,
            identifier = self.wizard_state.get('process_identifier'),
            input = worker_inputs,
            complex_input = self.wizard_state.get('complex_input_identifier'),
            output = ['output'])
        nodes = dict(source=source, worker=worker)
        return nodes

    def execute_workflow(self, appstruct):
        nodes = self.workflow_description()
        from phoenix.wps import execute_restflow
        return execute_restflow(self.request.wps, nodes)

    def success(self, appstruct):
        self.wizard_state.set('done', appstruct)
        logger.debug("appstruct %s", appstruct)
        if appstruct.get('is_favorite', False):
            self.favorite.set(appstruct.get('favorite_name', 'unknown'), {})
        
        execution = self.execute_workflow(appstruct)
        models.add_job(
            request = self.request,
            workflow = True,
            title = appstruct.get('title'),
            wps_url = execution.serviceInstance,
            status_location = execution.statusLocation,
            abstract = appstruct.get('abstract'),
            keywords = appstruct.get('keywords'))

    def previous_success(self, appstruct):
        self.success(appstruct)
        return self.previous()
    
    def next_success(self, appstruct):
        self.success(appstruct)
        self.wizard_state.clear()
        return HTTPFound(location=self.request.route_url('myjobs'))

    def appstruct(self):
        return self.wizard_state.get('done', {})

    def breadcrumbs(self):
        breadcrumbs = super(Done, self).breadcrumbs()
        breadcrumbs.append(dict(route_name='wizard_done', title=self.title))
        return breadcrumbs

    @view_config(route_name='wizard_done', renderer='phoenix:templates/wizard/default.pt')
    def view(self):
        return super(Done, self).view()
