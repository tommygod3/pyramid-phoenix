from pyramid.view import view_defaults
from deform import Form

from phoenix.esgfsearch.schema import ESGFSearchSchema
from phoenix.esgfsearch.search import ESGFSearch

import logging
LOGGER = logging.getLogger(__name__)


@view_defaults(permission='view', layout='default')
class ESGFSearchActions(object):
    def __init__(self, request):
        self.request = request
        self.esgfsearch = ESGFSearch(request)

    def search_files(self):
        return self.esgfsearch.search_files()

    def search_datasets(self):
        result = dict()
        result.update(self.esgfsearch.query_params())
        result.update(self.esgfsearch.search_datasets())
        result['form'] = Form(ESGFSearchSchema())
        result['quickview'] = True
        result['page'] = 0
        return result
