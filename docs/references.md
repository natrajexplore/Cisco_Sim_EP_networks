# Cisco DevNet resources used

## Always-on sandboxes (no VPN, no reservation)

| System | Base URL | Credentials | Notes |
|---|---|---|---|
| Catalyst Center (DNA Center) | `https://sandboxdnac.cisco.com` | `devnetuser` / `Cisco123!` | internal-CA cert → `verify=False`; ~4 devices, real Assurance data |
| Identity Services Engine | `https://devnetsandboxise.cisco.com` | `readonly` / `ISEisC00L` | ERS read-only (GET); confirm current creds on the sandbox page |

Sandbox catalog: <https://developer.cisco.com/site/sandbox/>
· Catalyst Center: <https://developer.cisco.com/docs/catalyst-center/sandboxes/>
· ISE: <https://developer.cisco.com/docs/identity-services-engine/latest/sandbox/>

> Credentials for shared always-on sandboxes rotate occasionally. If `netsim
> sandbox` shows `401`, log in to the DevNet sandbox page and update the
> `NETSIM_ISE_*` / `NETSIM_DNAC_*` values in `.env`.

## SDKs

| Package | Repo | Used for |
|---|---|---|
| `dnacentersdk` | `cisco-en-programmability/dnacentersdk` | Catalyst Center auth + `custom_caller` |
| `ciscoisesdk` | `cisco-en-programmability/ciscoisesdk` | ISE ERS auth + `custom_caller` |

## API shapes / sample data cross-referenced

* Catalyst Center Intent API — <https://developer.cisco.com/docs/catalyst-center/>
  (`/site`, `/network-device`, `/network-health`, `/client-health`, `/issues`,
  `/image/importation`, `/wireless/profile`)
* ISE ERS API — <https://developer.cisco.com/docs/identity-services-engine/>
  (`/ers/config/{networkdevice,authorizationprofile,downloadableacl,sgt,
  identitygroup,endpoint,endpointgroup,portal,guesttype,sponsorportal}`)
* `1homas/ise-postman-collections` — ERS/MNT/pxGrid request shapes
* `CiscoDevNet` org — ISE ERS and Catalyst Center sample code

## Endpoints that vary by sandbox

Some Assurance endpoints (client-health, device-health RF) are intermittently
available on the shared sandbox. Scenarios degrade to `warn`/`info` and, for RF,
fall back to a **deterministic synthetic RF model** seeded from the AP name so the
golden snapshot stays stable.
