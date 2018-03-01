from traitlets import (
    Instance, Type, Tuple, List, Dict, Integer, Unicode, Float, Any
)
from jupyterhub.spawner import Spawner
from kubespawner.spawner import KubeSpawner

class KubeProfileSpawner(KubeSpawner):
    
    UNDEFINED_DISPLAY_NAME = "?? undefined 'display_name' ??"

    form_template = Unicode(
        """<label for="profile">Please select a profile for your Jupyter instance:</label>
        <select class="form-control" name="profile" required autofocus>
        {input_template}
        </select>
        """,
        config = True,
        help = """Template to use to construct options_form text. {input_template} is replaced with
            the result of formatting input_template against each item in the profiles list."""
        )

    input_template = Unicode("""
        <option value="{key}" {first}>{display}</option>""",
        config = True,
        help = """Template to construct {input_template} in form_template. This text will be formatted
            against each item in the profiles list, in order, using the following key names:
            ( display, key, type ) for the first three items in the tuple, and additionally
            first = "checked" (taken from first_template) for the first item in the list, so that
            the first item starts selected."""
        )

    first_template = Unicode('selected',
        config=True,
        help="Text to substitute as {first} in input_template"
        )

    options_form = Unicode()
    
    single_user_profile_list = List(
        trait = Dict(),
        default_value = [],
        minlen = 1,
        config = True,
        help = """List of profiles to offer for selection. Signature is:
            List(Dict()), where each item is a dictionary that has two keys:
            - 'display_name': the human readable display name
            - 'kubespawner_overrride': a dictionary with overrides to apply to the KubeSpawner 
              settings."""
        )

    def __init__(self, *args, **kwargs):
        Spawner.__init__(self, *args, **kwargs)

    def _options_form_default(self):
        temp_keys = [
            {
                'display': p.get('display_name', self.UNDEFINED_DISPLAY_NAME), 
                'key': i, 
                'first': '',
        } for i, p in enumerate(self.single_user_profile_list)]
        temp_keys[0]['first'] = self.first_template
        text = ''.join([ self.input_template.format(**tk) for tk in temp_keys ])
        return self.form_template.format(input_template=text)

    def options_from_form(self, formdata):
        # Default to first profile if somehow none is provided
        selected_profile = int(formdata.get('profile',[0])[0])
        options = self.single_user_profile_list[selected_profile]
        self.log.debug("Applying KubeSpawner override for profile '%s'", 
                  options.get('display_name', self.UNDEFINED_DISPLAY_NAME))
        kubespawner_overrride = options.get('kubespawner_overrride', {})
        for k, v in kubespawner_overrride.items():
            setattr(self, k, v)
        return options