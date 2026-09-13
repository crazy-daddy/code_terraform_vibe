# Component: data_archive

> **Category:** Logistics & Orders | **Component Name:** Data Archive

Stores JSON-safe data that survives script restarts and save/load. Access the Data Archive with `get_component("notebook")` after its research unlocks. Use Libraries to share code and the Signal Bus to share temporary live state.

**Returned by:** `get_component("notebook")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.set(key, value)`

Store a JSON-safe value under a named key. The archive holds up to 512 entries; each value supports 8 nested levels, 16,384 total nodes counting values and containers, and 4,096 characters per string or dictionary key.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `string` | Archive key, 1-96 characters using letters, numbers, `_`, `.`, `:`, or `-` |
| `value` | `any` | JSON-safe value, up to 8 nested levels, 16,384 total nodes counting values and containers, and 4,096 characters per string or dictionary key |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"invalid_key"` | rejection | The supplied key is invalid. |
| `"entry_limit"` | rejection | The archive has reached its entry limit. |
| `"invalid_value"` | rejection | The supplied value is invalid. |

##### `.transaction(key, default, updater)`

Atomically transform one stored value within the same archive value limits. The updater may be any pure callable; it receives the latest value or supplied default and cannot sleep, yield, or mutate the world.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `string` | Archive key, 1-96 characters using letters, numbers, `_`, `.`, `:`, or `-` |
| `default` | `any` | JSON-safe value within the archive value limits, used when the key is missing |
| `updater` | `any` | Pure callable that receives the current value and returns the next value within the archive value limits |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"invalid_key"` | rejection | The supplied key is invalid. |
| `"entry_limit"` | rejection | The archive has reached its entry limit. |
| `"invalid_value"` | rejection | The supplied value is invalid. |
| `"busy"` | transient | The component is already performing another operation. |

##### `.get(key, default=None)`

Read a stored value by key. If the key is missing, returns the optional default argument; if no default is provided, returns `None`. Reading does not consume or modify the entry.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `string` | Archive key, 1-96 characters using letters, numbers, `_`, `.`, `:`, or `-` |
| `default` | `any` | Returned when the key is missing |

- **Returns** Stored value, the optional default, or `None`.

*Raises*

| Exception | Condition |
| --- | --- |
| `ValueError` | The archive key must be 1-96 characters using letters, numbers, `_`, `.`, `:`, or `-`, and cannot be a reserved object-field name. |

##### `.has(key)`

Return `True` when the archive contains the key, otherwise `False`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `string` | Archive key, 1-96 characters using letters, numbers, `_`, `.`, `:`, or `-` |

- **Returns** Boolean: `True` when the archive contains the key.

*Raises*

| Exception | Condition |
| --- | --- |
| `ValueError` | The archive key must be 1-96 characters using letters, numbers, `_`, `.`, `:`, or `-`, and cannot be a reserved object-field name. |

##### `.delete(key)`

Remove one key.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `string` | Archive key, 1-96 characters using letters, numbers, `_`, `.`, `:`, or `-` |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_found"` | rejection | The requested object, target, or record does not exist. |
| `"invalid_key"` | rejection | The supplied key is invalid. |

##### `.keys(prefix="")`

Return archive keys as a sorted list. Pass a prefix such as `"rover."` to list only matching keys.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `prefix` | `string` | Optional key prefix using the archive key character set |

- **Returns** Sorted list of archive keys, optionally filtered by prefix.

*Raises*

| Exception | Condition |
| --- | --- |
| `ValueError` | The archive prefix must use letters, numbers, `_`, `.`, `:`, or `-` and be at most 96 characters. |

##### `.clear(prefix="")`

Remove archived entries. With no prefix it clears the whole archive; with a prefix it clears matching keys.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `prefix` | `string` | Optional key prefix using the archive key character set |

- **Returns** `CountResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.count`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The command affected `.count` entries or units. |
| `"no_op"` | success | The command affected no entries or units. |
| `"invalid_key"` | rejection | The supplied key is invalid. |

*Components / Logistics & Orders*
