---
name: Feature request
about: Suggest an idea for this project

---

**Is your feature request related to a problem? Please describe.**
Currently, users rely solely on centrally managed hardware. There is no automated, self-serve way for users to contribute or connect their own hardware to the `qiip` network, nor is there a built-in permissions model to let users manage the hardware they contribute without being a global admin.

**Describe the solution you'd like**
Allow users to add their own hardware (nodes) to the platform with the following capabilities:

1. **Self-Serve Hardware Addition:** Users can add their own hardware and choose whether it should be used **publicly** (by anyone) or **privately**.
2. **Automatic Node Admin Permissions:** The user who adds the hardware automatically becomes an admin of that specific hardware/node. This must happen independently of their global `qiip` admin permissions (they do not need to be a global admin).
3. **Private Node Access Management:** If the node is set to "private", the node's detail page should include an invitation system. The node admin can invite other users to access the private node by passing their email addresses.

**Describe alternatives you've considered**
- A purely manual approach where users submit a request, and global admins manually register the hardware, attach it to a specific tenant/group, and manually configure RBAC. This creates a bottleneck and requires manual intervention.
- Allowing only public node contributions, but this discourages users who want to add dedicated compute for their own team/projects.

**Additional context**
This feature would greatly support a decentralized or community-driven hardware contribution model, making it easier for users to bring their own compute resources (BYOC) without compromising on privacy or putting administrative burden on the `qiip` maintainers.
