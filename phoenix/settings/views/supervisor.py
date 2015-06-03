from pyramid.view import view_config
from pyramid.httpexceptions import HTTPFound

from . import SettingsView

import logging
logger = logging.getLogger(__name__)

class Supervisor(SettingsView):
    def __init__(self, request):
        super(Supervisor, self).__init__(request, name='settings_supervisor', title='Supervisor')
        import xmlrpclib
        self.server = xmlrpclib.Server('http://localhost:9001/RPC2')

    def breadcrumbs(self):
        breadcrumbs = super(Supervisor, self).breadcrumbs()
        breadcrumbs.append(dict(route_path=self.request.route_path(self.name), title=self.title))
        return breadcrumbs

    @view_config(route_name="supervisor_program")
    def supervisor_program(self):
        action = self.request.matchdict.get('action')
        name = self.request.matchdict.get('name')

        if name == 'all':
            if action == 'start':
                self.server.supervisor.startAllProcesses()
                self.session.flash("All services started.", queue="success")
            elif action == 'stop':
                self.server.supervisor.stopAllProcesses()
                self.session.flash("All services stopped.", queue="danger")
            elif action == 'restart':
                self.server.supervisor.stopAllProcesses()
                self.server.supervisor.startAllProcesses()
                self.session.flash("All services restarted.", queue="success")
        else:
            if action == 'start':
                self.server.supervisor.startProcess(name)
                self.session.flash("Service {0} started.".format(name), queue="success")
            elif action == 'stop':
                self.server.supervisor.stopProcess(name)
                self.session.flash("Service {0} stopped.".format(name), queue="danger")
            elif action == 'restart':
                self.server.supervisor.stopProcess(name)
                self.server.supervisor.startProcess(name)
                self.session.flash("Service {0} restarted.".format(name), queue="success")
        
        return HTTPFound(location=self.request.route_path(self.name))
        
    @view_config(route_name="settings_supervisor", renderer='../templates/settings/supervisor.pt')
    def view(self):
        grid = Grid(self.request, self.server.supervisor.getAllProcessInfo(), ['state', 'description', 'name', ''])
        return dict(grid=grid)

from phoenix.grid import MyGrid
class Grid(MyGrid):
    def __init__(self, request, *args, **kwargs):
        super(Grid, self).__init__(request, *args, **kwargs)
        self.column_formats['state'] = self.state_td
        self.column_formats['description'] = self.description_td
        self.column_formats['name'] = self.name_td
        self.column_formats[''] = self.action_td
        self.exclude_ordering = self.columns

    def state_td(self, col_num, i, item):
        return self.render_label_td(item.get('statename'))
        
    def description_td(self, col_num, i, item):
        return self.render_label_td(item.get('description'))
    
    def name_td(self, col_num, i, item):
        return self.render_label_td(item.get('name'))

    def action_td(self, col_num, i, item):
        buttongroup = []
        if item.get('state') == 20:
            buttongroup.append(
                ("restart", item.get('name'), "fa fa-refresh", "",
                self.request.route_path('supervisor_program', action='restart', name=item.get('name')), False) )
            buttongroup.append(
                ("stop", item.get('name'), "fa fa-stop", "",
                self.request.route_path('supervisor_program', action='stop', name=item.get('name')), False) )
        else:
            buttongroup.append(
                ("start", item.get('name'), "fa fa-play", "",
                self.request.route_path('supervisor_program', action='start', name=item.get('name')), False) )
        buttongroup.append(
            ("clear", item.get('name'), "fa fa-eraser", "",
             self.request.route_path('supervisor_program', action='clear', name=item.get('name')), False) )
        buttongroup.append(
            ("tail", item.get('name'), "fa fa-align-left", "",
             self.request.route_path('supervisor_program', action='tail', name=item.get('name')), False) )
        return self.render_action_td(buttongroup)
       
