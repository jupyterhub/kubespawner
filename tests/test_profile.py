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
        spawner._populate_profile_list_defaults(unfilled_profile_list)
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
    profile_list = spawner._populate_profile_list_defaults(profile_list)
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
    profile_list = spawner._populate_profile_list_defaults(profile_list)
    with pytest.raises(ValueError):
        spawner._get_profile('does-not-exist', profile_list)
