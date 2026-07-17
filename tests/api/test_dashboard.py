"""Integration tests for the dashboard route and HTML content.

Tests cover:
- GET /dashboard returns 200 with text/html content type (DASH-01)
- Dashboard served by same app as API (DASH-03)
- HTML contains Simple.css CDN link and dashboard assets (TMPL-01, TMPL-02)
- Table structure with 10 column headers including GPU Vendor, GPU Model, State, Actions (NODE-01)
- Badge CSS classes for status, circuit breaker, and provisioning states (NODE-02)
- Manual setup toggle and QUADS status element (D-04, D-05, D-09)
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


class TestDashboardRoute:
    """GET /dashboard returns 200 HTML from the same app (DASH-01, DASH-03, TMPL-01)."""

    def test_dashboard_returns_200(self, client: TestClient) -> None:
        """GET /dashboard returns status code 200."""
        response = client.get("/dashboard")
        assert response.status_code == 200

    def test_dashboard_returns_html(self, client: TestClient) -> None:
        """Response content-type contains text/html."""
        response = client.get("/dashboard")
        assert "text/html" in response.headers["content-type"]

    def test_dashboard_served_by_same_app(self, client: TestClient) -> None:
        """TestClient (wrapping create_app()) serves /dashboard -- proves DASH-03."""
        # The client fixture uses the same FastAPI app that serves /admin/nodes.
        # If this request succeeds, the dashboard shares the app.
        admin_response = client.get("/admin/nodes")
        dashboard_response = client.get("/dashboard")
        assert admin_response.status_code == 200
        assert dashboard_response.status_code == 200


class TestDashboardTemplate:
    """Dashboard HTML includes expected asset references (TMPL-01, TMPL-02)."""

    def test_contains_simple_css_cdn_link(self, client: TestClient) -> None:
        """HTML contains the Simple.css CDN link."""
        response = client.get("/dashboard")
        assert "cdn.simplecss.org/simple.css" in response.text

    def test_contains_dashboard_css_link(self, client: TestClient) -> None:
        """HTML contains link to dashboard.css."""
        response = client.get("/dashboard")
        assert "dashboard.css" in response.text

    def test_contains_dashboard_js_script(self, client: TestClient) -> None:
        """HTML contains script tag for dashboard.js."""
        response = client.get("/dashboard")
        assert "dashboard.js" in response.text

    def test_simple_css_loaded_before_dashboard_css(self, client: TestClient) -> None:
        """Simple.css CDN link appears before dashboard.css link in the HTML."""
        response = client.get("/dashboard")
        simple_pos = response.text.index("cdn.simplecss.org/simple.css")
        dashboard_pos = response.text.index("dashboard.css")
        assert simple_pos < dashboard_pos


class TestDashboardTableStructure:
    """Dashboard HTML contains the node fleet table structure (NODE-01, D-01, D-02)."""

    def test_contains_all_ten_column_headers(self, client: TestClient) -> None:
        """HTML contains all 10 th elements for the node table."""
        response = client.get("/dashboard")
        headers = [
            "Node ID",
            "GPU Vendor",
            "GPU Model",
            "Endpoint",
            "Model",
            "State",
            "Active Connections",
            "Circuit Breaker",
            "Requests",
            "Actions",
        ]
        for header in headers:
            assert header in response.text, f"Missing column header: {header}"

    def test_contains_requests_column_header(self, client: TestClient) -> None:
        """HTML contains the Requests column header (METR-02)."""
        response = client.get("/dashboard")
        assert "Requests" in response.text

    def test_contains_table_body_id(self, client: TestClient) -> None:
        """HTML contains tbody with id="node-table-body" for JS population."""
        response = client.get("/dashboard")
        assert 'id="node-table-body"' in response.text


class TestDashboardPolling:
    """Dashboard HTML includes polling configuration (DASH-02)."""

    def test_contains_poll_interval_js_variable(self, client: TestClient) -> None:
        """HTML contains POLL_INTERVAL_MS JavaScript variable."""
        response = client.get("/dashboard")
        assert "POLL_INTERVAL_MS" in response.text

    def test_poll_interval_default_value(self, client: TestClient) -> None:
        """Default poll interval is 10s = 10000ms in the JS variable."""
        response = client.get("/dashboard")
        assert "10000" in response.text

    def test_contains_last_updated_element(self, client: TestClient) -> None:
        """HTML contains element with id='last-updated'."""
        response = client.get("/dashboard")
        assert 'id="last-updated"' in response.text

    def test_contains_poll_warning_element(self, client: TestClient) -> None:
        """HTML contains element with id='poll-warning'."""
        response = client.get("/dashboard")
        assert 'id="poll-warning"' in response.text

    def test_contains_quads_status_element(self, client: TestClient) -> None:
        """HTML contains span with id='quads-status' for QUADS indicator (D-09)."""
        response = client.get("/dashboard")
        assert 'id="quads-status"' in response.text


class TestDashboardBadgeCSS:
    """Badge CSS contains classes for all status and circuit breaker states (NODE-02)."""

    _css_path = (
        Path(__file__).resolve().parent.parent.parent
        / "inference_proxy"
        / "static"
        / "css"
        / "dashboard.css"
    )

    def test_badge_css_contains_all_status_classes(self) -> None:
        """dashboard.css contains .badge-healthy, .badge-unhealthy, .badge-draining."""
        css = self._css_path.read_text()
        for cls in (".badge-healthy", ".badge-unhealthy", ".badge-draining"):
            assert cls in css, f"Missing CSS class: {cls}"

    def test_badge_css_contains_all_cb_classes(self) -> None:
        """dashboard.css contains .badge-closed, .badge-open, .badge-half_open."""
        css = self._css_path.read_text()
        for cls in (".badge-closed", ".badge-open", ".badge-half_open"):
            assert cls in css, f"Missing CSS class: {cls}"

    def test_badge_css_contains_provisioning_classes(self) -> None:
        """dashboard.css contains .badge-complete, .badge-failed, .badge-in-progress."""
        css = self._css_path.read_text()
        for cls in (".badge-complete", ".badge-failed", ".badge-in-progress"):
            assert cls in css, f"Missing CSS class: {cls}"

    def test_badge_css_contains_available_class(self) -> None:
        """dashboard.css contains .badge-available for available state badge (DASH-01)."""
        css = self._css_path.read_text()
        assert ".badge-available" in css, "Missing CSS class: .badge-available"

    def test_badge_css_contains_action_button_classes(self) -> None:
        """dashboard.css contains .btn-setup and .btn-teardown action variants (D-06)."""
        css = self._css_path.read_text()
        assert ".btn-setup" in css, "Missing CSS class: .btn-setup"
        assert ".btn-teardown" in css, "Missing CSS class: .btn-teardown"


class TestSetupForm:
    """Dashboard HTML contains the setup form elements (DASH-01, D-04, D-05)."""

    def test_contains_setup_form(self, client: TestClient) -> None:
        """HTML contains form with id='setup-form' (moved inside Node Fleet card)."""
        response = client.get("/dashboard")
        assert 'id="setup-form"' in response.text

    def test_standalone_provision_card_removed(self, client: TestClient) -> None:
        """Standalone 'Provision Node' card is removed (D-04)."""
        response = client.get("/dashboard")
        assert "Provision Node" not in response.text

    def test_contains_manual_setup_toggle(self, client: TestClient) -> None:
        """HTML contains manual setup toggle link (D-05)."""
        response = client.get("/dashboard")
        assert 'id="manual-setup-toggle"' in response.text
        assert "+ Manual setup" in response.text

    def test_contains_manual_setup_row(self, client: TestClient) -> None:
        """HTML contains hidden manual setup row container."""
        response = client.get("/dashboard")
        assert 'id="manual-setup-row"' in response.text

    def test_contains_hostname_input(self, client: TestClient) -> None:
        """HTML contains input with id='setup-hostname'."""
        response = client.get("/dashboard")
        assert 'id="setup-hostname"' in response.text

    def test_contains_setup_button(self, client: TestClient) -> None:
        """HTML contains button with id='setup-btn'."""
        response = client.get("/dashboard")
        assert 'id="setup-btn"' in response.text


class TestTasksPanel:
    """Dashboard HTML contains the provisioning tasks panel (DASH-03)."""

    def test_contains_tasks_panel(self, client: TestClient) -> None:
        """HTML contains section with id='tasks-panel'."""
        response = client.get("/dashboard")
        assert 'id="tasks-panel"' in response.text

    def test_contains_tasks_table_body(self, client: TestClient) -> None:
        """HTML contains tbody with id='tasks-table-body'."""
        response = client.get("/dashboard")
        assert 'id="tasks-table-body"' in response.text
