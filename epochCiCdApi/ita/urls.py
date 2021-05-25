#   Copyright 2019 NEC Corporation
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

from django.urls import path, include
from . import views
from . import viewsManifestParameter
from . import viewsManifestTemplates
from . import viewsManifestGitEnv
from . import viewsConductorExec
from . import viewsInitialize

urlpatterns = [
    # create ITA pod
    path('', views.index),
    # 
    path('initialize', viewsInitialize.post),
    # GitEnv
    path('manifestGitEnv', viewsManifestGitEnv.index),
    # Parameter
    path('manifestParameter', viewsManifestParameter.post),
    # Template
    path('manifestTemplates', viewsManifestTemplates.post),
    # execute conductor
    path('cdExec', viewsConductorExec.index),
]
