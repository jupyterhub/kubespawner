import pytest

from kubespawner import KubeSpawner


@pytest.mark.parametrize(
    "unfilled_profile_list,filled_profile_list",
    [
        (
            [
                {
                    'display_name': 'Something without a slug',
                    'kubespawner_override': {},
                },
                {
                    'display_name': 'Something with a slug',
                    'slug': 'sluggity-slug',
                    'kubespawner_override': {},
                },
            ],
            [
                {
                    'display_name': 'Something without a slug',
                    'slug': 'something-without-a-slug',
                    'default': True,
                    'kubespawner_override': {},
                },
                {
                    'display_name': 'Something with a slug',
                    'slug': 'sluggity-slug',
                    'kubespawner_override': {},
                },
            ],
        ),
        (
            [
                {
                    'display_name': 'Something without choices',
                    'kubespawner_override': {},
                },
                {
                    'display_name': 'Something with choices',
                    'kubespawner_override': {},
                    'default': True,
                    'profile_options': {
                        'no-defaults': {
                            'display_name': 'Some choice without a default set',
                            'choices': {
                                'option-1': {
                                    'display_name': 'Option 1',
                                    'kubespawner_override': {},
                                },
                                'option-2': {
                                    'display_name': 'Option 2',
                                    'kubespawner_override': {},
                                },
                            },
                        },
                        'only-unlisted': {
                            'display_name': 'Some option without any choices set',
                            'unlisted_choice': {'enabled': True},
                        },
                        'explicit-defaults': {
                            'display_name': 'Some choice with a default set',
                            'choices': {
                                'option-1': {
                                    'display_name': 'Option 1',
                                    'kubespawner_override': {},
                                },
                                'option-2': {
                                    'display_name': 'Option 2',
                                    'default': True,
                                    'kubespawner_override': {},
                                },
                            },
                        },
                    },
                },
            ],
            [
                {
                    'display_name': 'Something without choices',
                    'slug': 'something-without-choices',
                    'kubespawner_override': {},
                },
                {
                    'display_name': 'Something with choices',
                    'slug': 'something-with-choices',
                    'default': True,
                    'kubespawner_override': {},
                    'profile_options': {
                        'no-defaults': {
                            'display_name': 'Some choice without a default set',
                            'unlisted_choice': {'enabled': False},
                            'choices': {
                                'option-1': {
                                    'display_name': 'Option 1',
                                    'default': True,
                                    'kubespawner_override': {},
                                },
                                'option-2': {
                                    'display_name': 'Option 2',
                                    'kubespawner_override': {},
                                },
                            },
                        },
                        'only-unlisted': {
                            'display_name': 'Some option without any choices set',
                            'unlisted_choice': {
                                'enabled': True,
                                'display_name_in_choices': 'Other...',
                            },
                        },
                        'explicit-defaults': {
                            'display_name': 'Some choice with a default set',
                            'unlisted_choice': {'enabled': False},
                            'choices': {
                                'option-1': {
                                    'display_name': 'Option 1',
                                    'kubespawner_override': {},
                                },
                                'option-2': {
                                    'display_name': 'Option 2',
                                    'default': True,
                                    'kubespawner_override': {},
                                },
                            },
                        },
                    },
                },
            ],
        ),
        ([], []),
    ],
)
async def test_profile_missing_defaults_populated(
    unfilled_profile_list, filled_profile_list
):
    """
    Tests that missing profileList values are populated
    """
    spawner = KubeSpawner(_mock=True)
    assert (
        spawner._get_initialized_profile_list(unfilled_profile_list)
        == filled_profile_list
    )


@pytest.mark.parametrize(
    "profile_list,slug,selected_profile",
    [
        (
            [
                {
                    'display_name': 'profile 1',
                    'kubespawner_override': {},
                },
                {
                    'display_name': 'profile 2',
                    'kubespawner_override': {},
                },
            ],
            'profile-2',
            {
                'display_name': 'profile 2',
                'slug': 'profile-2',
                'kubespawner_override': {},
            },
        ),
        (
            [
                {
                    'display_name': 'profile 1',
                    'kubespawner_override': {},
                },
                {
                    'display_name': 'profile 2',
                    'default': True,
                    'kubespawner_override': {},
                },
            ],
            None,
            {
                'display_name': 'profile 2',
                'slug': 'profile-2',
                'default': True,
                'kubespawner_override': {},
            },
        ),
        (
            [
                {
                    'display_name': 'profile 1',
                    'kubespawner_override': {},
                },
                {
                    'display_name': 'profile 2',
                    'default': True,
                    'kubespawner_override': {},
                },
            ],
            '',
            {
                'display_name': 'profile 2',
                'slug': 'profile-2',
                'default': True,
                'kubespawner_override': {},
            },
        ),
    ],
)
async def test_find_slug(profile_list, slug, selected_profile):
    """
    Test that we can find the profile we expect given slugs
    """
    spawner = KubeSpawner(_mock=True)
    profile_list = spawner._get_initialized_profile_list(profile_list)
    assert spawner._get_profile(slug, profile_list) == selected_profile


async def test_find_slug_exception():
    """
    Test that looking for a slug that doesn't exist gives us an exception
    """
    spawner = KubeSpawner(_mock=True)
    profile_list = [
        {
            'display_name': 'profile 1',
            'kubespawner_override': {},
        },
        {
            'display_name': 'profile 2',
            'kubespawner_override': {},
        },
    ]
    profile_list = spawner._get_initialized_profile_list(profile_list)
    with pytest.raises(ValueError):
        spawner._get_profile('does-not-exist', profile_list)


async def test_unlisted_choice_non_string_override():
    profiles = [
        {
            'display_name': 'CPU only',
            'slug': 'cpu',
            'profile_options': {
                'image': {
                    'display_name': 'Image',
                    'unlisted_choice': {
                        'enabled': True,
                        'display_name': 'Image Location',
                        'validation_regex': '^pangeo/.*$',
                        'validation_message': 'Must be a pangeo image, matching ^pangeo/.*$',
                        'kubespawner_override': {
                            'image': '{value}',
                            'environment': {
                                'CUSTOM_IMAGE_USED': 'yes',
                                'CUSTOM_IMAGE': '{value}',
                                # This should just be passed through, as JUPYTER_USER is not replaced
                                'USER': '${JUPYTER_USER}',
                                # This should render as ${JUPYTER_USER}, as the {{ and }} escape them.
                                # this matches existing behavior for other replacements elsewhere
                                'USER_TEST': '${{JUPYTER_USER}}',
                            },
                            "init_containers": [
                                {
                                    "name": "testing",
                                    "image": "{value}",
                                    "securityContext": {"runAsUser": 1000},
                                }
                            ],
                        },
                    },
                }
            },
        },
    ]
    spawner = KubeSpawner(_mock=True)
    spawner.profile_list = profiles

    image = "pangeo/pangeo-notebook:latest"
    # Set user option for image directly
    spawner.user_options = {"profile": "cpu", "image--unlisted-choice": image}

    # this shouldn't error
    await spawner.load_user_options()

    assert spawner.image == image
    assert spawner.environment == {
        'CUSTOM_IMAGE_USED': 'yes',
        'CUSTOM_IMAGE': image,
        'USER': '${JUPYTER_USER}',
        'USER_TEST': '${JUPYTER_USER}',
    }
    assert spawner.init_containers == [
        {"name": "testing", "image": image, 'securityContext': {'runAsUser': 1000}}
    ]


async def test_empty_user_options_and_profile_options_api():
    profiles = [
        {
            'display_name': 'CPU only',
            'profile_options': {
                'image': {
                    'display_name': 'Image',
                    'unlisted_choice': {
                        'enabled': True,
                        'display_name': 'Image Location',
                        'validation_regex': '^pangeo/.*$',
                        'validation_message': 'Must be a pangeo image, matching ^pangeo/.*$',
                        'kubespawner_override': {'image': '{value}'},
                    },
                    "choices": {
                        'op-1': {
                            'display_name': 'Option 1',
                            'kubespawner_override': {
                                'image': 'pangeo/pangeo-notebook:ebeb9dd'
                            },
                        },
                        'op-2': {
                            'display_name': 'Option 2',
                            'kubespawner_override': {
                                'image': 'pangeo/pangeo-notebook:latest'
                            },
                        },
                    },
                }
            },
        },
    ]
    spawner = KubeSpawner(_mock=True)
    spawner.profile_list = profiles
    # set user_options directly (e.g. via api)
    spawner.user_options = {}

    # nothing should be loaded yet
    assert spawner.cpu_limit is None

    # this shouldn't error
    await spawner.load_user_options()

    # implicit defaults should be used
    assert spawner.image == "pangeo/pangeo-notebook:ebeb9dd"


@pytest.mark.parametrize(
    "profile_list, formdata",
    [
        (
            [
                {
                    "display_name": "short",
                    "slug": "short",
                    "profile_options": {
                        "relevant": {
                            "choices": {
                                "choice-a": {
                                    "kubespawner_override": {},
                                },
                            },
                        },
                    },
                },
                {
                    "display_name": "short-plus",
                    "slug": "short-plus",
                    "profile_options": {
                        "irrelevant": {
                            "choices": {
                                "choice-b": {
                                    "kubespawner_override": {},
                                },
                            },
                        },
                    },
                },
            ],
            # What is below is hardcoded based on what is above and based on
            # how the HTML form looks currently. If that changes, whats below needs
            # to change as well.
            {
                'profile': ['short'],
                'profile-option-short--relevant': ['choice-a'],
                'profile-option-short-plus--irrelevant': ['choice-b'],
            },
        ),
    ],
)
async def test_profile_slug_and_option_slug_mixup(profile_list, formdata):
    """
    If we have a profile list with two entries, their respective profile_options
    should not be mixed up with each other. This has happened when one profile
    list entry was named like another but shorter.
    """
    spawner = KubeSpawner(_mock=True)
    spawner.profile_list = profile_list

    user_options = spawner.options_from_form(formdata)
    assert user_options.get("profile") == "short"
    assert user_options.get("relevant") == "choice-a"
    assert not user_options.get("plus-irrelevant")
