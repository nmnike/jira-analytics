"""Tests for SyncService."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.sync_service import SyncService, SyncStats
from app.connectors.schemas import (
    JiraProjectSchema,
    JiraUserSchema,
)


class TestSyncStats:
    """Tests for SyncStats."""
    
    def test_initial_stats(self):
        """Test that initial stats are zero."""
        stats = SyncStats()
        
        assert stats.projects_synced == 0
        assert stats.issues_synced == 0
        assert stats.worklogs_synced == 0
        assert stats.errors == []
    
    def test_duration_calculation(self):
        """Test duration calculation."""
        stats = SyncStats()
        stats.started_at = datetime(2024, 1, 1, 10, 0, 0)
        stats.finished_at = datetime(2024, 1, 1, 10, 1, 30)
        
        assert stats.duration_seconds == 90.0
    
    def test_to_dict(self):
        """Test stats serialization."""
        stats = SyncStats()
        stats.projects_synced = 5
        stats.projects_created = 3
        stats.finish()
        
        result = stats.to_dict()
        
        assert result["projects"]["synced"] == 5
        assert result["projects"]["created"] == 3
        assert "duration_seconds" in result


class TestSyncServiceUpsert:
    """Tests for SyncService upsert methods."""
    
    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return MagicMock()
    
    @pytest.fixture
    def mock_jira(self):
        """Create mock Jira client."""
        return AsyncMock()
    
    def test_upsert_project(self, mock_db, mock_jira):
        """Test project upsert from Jira data."""
        service = SyncService(mock_db, mock_jira)
        
        jira_project = JiraProjectSchema(
            id="10001",
            key="PRJ",
            name="Test Project",
            description="Description",
            projectTypeKey="software"
        )
        
        # Mock the repository
        service.project_repo = MagicMock()
        service.project_repo.upsert_by_field.return_value = (MagicMock(), True)
        
        project, created = service._upsert_project(jira_project)
        
        service.project_repo.upsert_by_field.assert_called_once()
        call_args = service.project_repo.upsert_by_field.call_args
        assert call_args[0][0] == "jira_project_id"
        assert call_args[0][1] == "10001"
    
    def test_ensure_employee(self, mock_db, mock_jira):
        """Test employee creation from Jira user."""
        service = SyncService(mock_db, mock_jira)
        
        jira_user = JiraUserSchema(
            accountId="user123",
            displayName="John Doe",
            emailAddress="john@example.com",
            active=True
        )
        
        # Mock the repository
        service.employee_repo = MagicMock()
        mock_employee = MagicMock()
        service.employee_repo.upsert_by_field.return_value = (mock_employee, True)
        
        employee = service._ensure_employee(jira_user)
        
        assert employee == mock_employee
        assert service.stats.employees_created == 1
        assert service.stats.employees_synced == 1
