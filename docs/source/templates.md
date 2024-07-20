(templates)=

# Templated fields

Several fields in KubeSpawner can be resolved as string templates,
so each user server can get distinct values from the same configuration.

String templates use the Python formatting convention of `f"{fieldname}"`,
so for example the default `pod_name_template` of `"jupyter-{user_server}"` will produce:

| username         | server name | pod name                                       |
| ---------------- | ----------- | ---------------------------------------------- |
| `user`           | `''`        | `jupyter-user`                                 |
| `user`           | `server`    | `jupyter-user--server`                         |
| `user@email.com` | `Some Name` | `jupyter-user-email-com--some-name---0c1fe94b` |

## templated properties

Some common templated fields:

- [pod_name_template](#KubeSpawner.pod_name_template)
- [pvc_name_template](#KubeSpawner.pvc_name_template)
- [working_dir](#KubeSpawner.working_dir)

## fields

The following fields are available in templates:

| field                    | description                                                                                                                                                  |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `{username}`             | the username passed through the configured slug scheme                                                                                                       |
| `{servername}`           | the name of the server passed through the configured slug scheme (`''` for the user's default server)                                                        |
| `{user_server}`          | the username and servername together as a single slug. This should be used most places for a unique string for a given user's server (new in kubespawner 7). |
| `{unescaped_username}`   | the actual username without escaping (no guarantees about value, except as enforced by your Authenticator)                                                   |
| `{unescaped_servername}` | the actual server name without escaping (no guarantees about value)                                                                                          |
| `{pod_name}`             | the resolved pod name, often a good choice if you need a starting point for other resources (new in kubespawner 7)                                           |
| `{pvc_name}`             | the resolved PVC name (new in kubespawner 7)                                                                                                                 |
| `{namespace}`            | the kubernetes namespace of the server (new in kubespawner 7)                                                                                                |
| `{hubnamespace}`         | the kubernetes namespace of the Hub                                                                                                                          |

Because there are two escaping schemes for `username`, `servername`, and `user_server`, you can explicitly select one or the other on a per-template-field basis with the prefix `safe_` or `escaped_`:

| field                   | description                                                                                                                                         |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `{escaped_username}`    | the username passed through the old 'escape' slug scheme                                                                                            |
| `{escaped_servername}`  | the server name passed through the 'escape' slug scheme                                                                                             |
| `{escaped_user_server}` | the username and servername together as a single slug, identical to `"{escaped_username}--{escaped_servername}".rstrip("-")` (new in kubespawner 7) |
| `{safe_username}`       | the username passed through the 'safe' slug scheme (new in kubespawner 7)                                                                           |
| `{safe_servername}`     | the server name passed through the 'safe' slug scheme (new in kubespawner 7)                                                                        |
| `{safe_user_server}`    | the username and server name together as a 'safe' slug (new in kubespawner 7)                                                                       |

These may be useful during a transition upgrading a deployment from an earlier version of kubespawner.

The value of the unprefixed `username`, etc. is goverend by the [](#KubeSpawner.slug_scheme) configuration, and always matches exactly one of these values.

## Template tips

In general, these guidelines should help you pick fields to use in your template strings:

- use `{user_server}` when a string should be unique _per server_ (e.g. pod name)
- use `{username}` when it should be unique per user, but shared across named servers (sometimes chosen for PVCs)
- use `{escaped_}` prefix if you need to keep certain values unchanged in a deployment upgrading from kubespawner \< 7
- `{pod_name}` can be re-used anywhere you want to create more resources associated with a given pod,
  to avoid repeating yourself

## Changing template configuration

Changing configuration should not generally affect _running_ servers.
However, when changing a property that may need to persist across user server restarts, special consideration may be required.
For example, changing `pvc_name` or `working_dir` could result in disconnecting a user's server from data loaded in previous sessions.
This may be your intention or not! KubeSpawner cannot know.

`pvc_name` is handled specially, to avoid losing access to data.
If `KubeSpawner.remember_pvc_name` is True, once a server has started, a server's PVC name cannot be changed by configuration.
Any future launch will use the previous `pvc_name`, regardless of change in configuration.
If you _want_ to change the names of mounted PVCs, you can set

```python
c.KubeSpawner.remember_pvc_name = False
```

This handling isn't general for PVCs, only specifically the default `pvc_name`.
If you have defined your own volumes, you need to handle changes to these yourself.

## Upgrading from kubespawner \< 7

Prior to kubespawner 7, an escaping scheme was used that ensured values were _unique_,
but did not always ensure fields were _valid_.
In particular:

- start/end rules were not enforced
- length was not enforced

This meant that e.g. usernames that start with a capital letter or were very long could result in servers failing to start because the escaping scheme produced an invalid label.
To solve this, a new 'safe' scheme has been added in kubespawner 7 for computing template strings,
which aims to guarantee to always produce valid object names and labels.
The new scheme is the default in kubespawner 7.

You can select the scheme with:

```python
c.KubeSpawner.slug_scheme = "escape"  # no changes from kubespawner 6
c.KubeSpawner.slug_scheme = "safe"  # default for kubespawner 7
```

The new scheme has the following rules:

- the length of any _single_ template field is limited to 48 characters (the total length of the string is not enforced)
- the result will only contain lowercase ascii letters, numbers, and `-`
- it will always start and end with a letter or number
- if a name is 'safe', it is used unmodified
- if any escaping is required, a truncated safe subset of characters is used, followed by `---{hash}` where `{hash}` is a checksum of the original input string
- `-` shall not occur in sequences of more than one consecutive `-`, except where inserted by the escaping mechanism
- if no safe characters are present, 'x' is used for the 'safe' subset

Since length requirements are applied on a per-field basis, a new `{user_server}` field is added,
which computes a single valid slug following the above rules which is unique for a given user server.
The general form is:

```
{username}--{servername}---{hash}
```

where

- `--{servername}` is only present for non-empty server names
- `---{hash}` is only present if escaping is required for _either_ username or servername, and hashes the combination of user and server.

This `{user_server}` is the recommended value to use in pod names, etc.
In the escape scheme, `{user_server}` is identical to the previous value used in default templates: `{username}--{servername}`,
so it should be safe to upgrade previous templated using `{username}--{servername}` to `{user_server}` or `{escaped_user_server}`.

In the vast majority of cases (where no escaping is required), the 'safe' scheme produces identical results to the 'escape' scheme.
Probably the most common case where the two differ is in the presence of single `-` characters, which the `escape` scheme escaped to `-2d`, while the 'safe' scheme does not.

Examples:

| name                                                                | escape scheme                                                                                       | safe scheme                                        |
| ------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| `username`                                                          | `username`                                                                                          | `username`                                         |
| `has-hyphen`                                                        | `has-2dhyphen`                                                                                      | `has-hyphen`                                       |
| `Capital`                                                           | `-43apital` (error)                                                                                 | `capital---1a1cf792`                               |
| `user@email.com`                                                    | `user-40email-2ecom`                                                                                | `user-email-com---0925f997`                        |
| `a-very-long-name-that-is-too-long-for-sixty-four-character-labels` | `a-2dvery-2dlong-2dname-2dthat-2dis-2dtoo-2dlong-2dfor-2dsixty-2dfour-2dcharacter-2dlabels` (error) | `a-very-long-name-that-is-too-long-for---29ac5fd2` |
| `ALLCAPS`                                                           | `-41-4c-4c-43-41-50-53` (error)                                                                     | `allcaps---27c6794c`                               |

Most changed names won't have a practical effect.
However, to avoid `pvc_name` changing even though KubeSpawner 6 didn't persist it,
on first launch (for each server) after upgrade KubeSpawner checks if:

1. `pvc_name_template` produces a different result with `scheme='escape'`
1. a pvc with the old 'escaped' name exists

and if such a pvc exists, the older name is used instead of the new one (it is then remembered for subsequent launches, according to `remember_pvc_name`).
This is an attempt to respect the `remember_pvc_name` configuration, even though the old name is not technically recorded.
We can infer the old value, as long as configuration has not changed.
This will only work if upgrading KubeSpawer does not _also_ coincide with a change in the `pvc_name_template` configuration.
