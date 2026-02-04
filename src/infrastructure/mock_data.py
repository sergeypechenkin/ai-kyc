"""Mock data service using pandas for CSV-based data access."""

import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


class CustomerRepository:
    """Repository for accessing customer data from CSV files.

    Provides methods to query customer profiles, documents, accounts,
    and KYC status from the mock data files.
    """

    def __init__(self, data_dir: str | Path | None = None):
        """Initialize the repository.

        Args:
            data_dir: Path to the data/mock directory. Defaults to project root.
        """
        if data_dir is None:
            # Find project root (where pyproject.toml is)
            current = Path(__file__).parent
            while current != current.parent:
                if (current / "pyproject.toml").exists():
                    data_dir = current / "data" / "mock"
                    break
                current = current.parent
            else:
                data_dir = Path("data/mock")

        self._data_dir = Path(data_dir)
        self._load_data()

    def _load_data(self) -> None:
        """Load all CSV files into memory."""
        self._customers = self._load_csv("customers.csv")
        self._documents = self._load_csv("kyc_documents.csv")
        self._history = self._load_csv("verification_history.csv")
        self._accounts = self._load_csv("accounts.csv")
        self._pep_watchlist = self._load_csv("pep_watchlist.csv")

    def _load_csv(self, filename: str) -> pd.DataFrame:
        """Load a CSV file into a DataFrame.

        Args:
            filename: Name of the CSV file

        Returns:
            DataFrame with the CSV data, or empty DataFrame if file not found
        """
        filepath = self._data_dir / filename
        if filepath.exists():
            return pd.read_csv(filepath, dtype=str).fillna("")
        return pd.DataFrame()

    def reload(self) -> None:
        """Reload all data from disk (for hot-reload support)."""
        self._load_data()

    def get_by_id(self, customer_id: str) -> dict[str, Any] | None:
        """Get customer by ID.

        Args:
            customer_id: Customer ID (e.g., "C001")

        Returns:
            Customer dict or None if not found
        """
        if self._customers.empty:
            return None

        matches = self._customers[self._customers["id"] == customer_id]
        if matches.empty:
            return None

        return matches.iloc[0].to_dict()

    def get_by_email(self, email: str) -> dict[str, Any] | None:
        """Get customer by email.

        Args:
            email: Customer email address

        Returns:
            Customer dict or None if not found
        """
        if self._customers.empty:
            return None

        matches = self._customers[
            self._customers["email"].str.lower() == email.lower()
        ]
        if matches.empty:
            return None

        return matches.iloc[0].to_dict()

    def search_by_name(self, name: str) -> list[dict[str, Any]]:
        """Search customers by name (first or last).

        Args:
            name: Name to search for

        Returns:
            List of matching customers
        """
        if self._customers.empty:
            return []

        name_lower = name.lower()
        matches = self._customers[
            self._customers["first_name"].str.lower().str.contains(name_lower)
            | self._customers["last_name"].str.lower().str.contains(name_lower)
        ]

        return matches.to_dict("records")

    def get_kyc_status(self, customer_id: str) -> dict[str, Any] | None:
        """Get KYC status for a customer.

        Args:
            customer_id: Customer ID

        Returns:
            KYC status dict with documents and overall status
        """
        # Get documents for customer
        docs = self._documents[self._documents["customer_id"] == customer_id]
        if docs.empty:
            return None

        # Get latest history entry
        history = self._history[self._history["customer_id"] == customer_id]
        latest_status = "unknown"
        last_review = None
        if not history.empty:
            latest = history.sort_values("timestamp", ascending=False).iloc[0]
            latest_status = latest["status"]
            last_review = latest["timestamp"]

        return {
            "customer_id": customer_id,
            "overall_status": latest_status,
            "last_review_date": last_review,
            "documents": docs.to_dict("records"),
        }

    def get_document(self, customer_id: str, doc_type: str) -> dict[str, Any] | None:
        """Get a specific document for a customer.

        Args:
            customer_id: Customer ID
            doc_type: Document type (passport, driving_license, utility_bill)

        Returns:
            Document dict or None
        """
        if self._documents.empty:
            return None

        matches = self._documents[
            (self._documents["customer_id"] == customer_id)
            & (self._documents["doc_type"] == doc_type)
        ]

        if matches.empty:
            return None

        return matches.iloc[0].to_dict()

    def get_accounts(self, customer_id: str) -> list[dict[str, Any]]:
        """Get all accounts for a customer.

        Args:
            customer_id: Customer ID

        Returns:
            List of account dicts
        """
        if self._accounts.empty:
            return []

        matches = self._accounts[self._accounts["customer_id"] == customer_id]
        # Convert balance to float for formatting
        accounts = matches.to_dict("records")
        for acc in accounts:
            try:
                acc["balance"] = float(acc["balance"])
            except (ValueError, TypeError):
                acc["balance"] = 0.0
        return accounts

    def update_kyc_status(
        self,
        customer_id: str,
        status: str,
        reviewer: str,
        notes: str = "",
    ) -> bool:
        """Update KYC status for a customer.

        Args:
            customer_id: Customer ID
            status: New status (approved, rejected, pending, pending_documents)
            reviewer: Reviewer ID or name
            notes: Optional notes

        Returns:
            True if updated successfully
        """
        # In a real app, this would write to DB. Here we just add to history DataFrame.
        new_entry = {
            "id": f"V{len(self._history) + 1:03d}",
            "customer_id": customer_id,
            "action": "status_update",
            "status": status,
            "reviewer_id": reviewer,
            "timestamp": datetime.now().isoformat(),
            "notes": notes,
        }

        self._history = pd.concat(
            [self._history, pd.DataFrame([new_entry])],
            ignore_index=True,
        )

        return True

    def get_pending_reviews(self) -> list[dict[str, Any]]:
        """Get all customers with pending KYC reviews.

        Returns:
            List of pending review records
        """
        if self._history.empty:
            return []

        # Get latest status for each customer
        latest = self._history.sort_values("timestamp", ascending=False).drop_duplicates(
            subset=["customer_id"], keep="first"
        )

        # Filter to pending statuses
        pending_statuses = ["pending", "pending_documents"]
        pending = latest[latest["status"].isin(pending_statuses)]

        # Enrich with customer names
        results = []
        for _, row in pending.iterrows():
            customer = self.get_by_id(row["customer_id"])
            customer_name = (
                f"{customer['first_name']} {customer['last_name']}"
                if customer
                else "Unknown"
            )
            results.append({
                "customer_id": row["customer_id"],
                "customer_name": customer_name,
                "status": row["status"],
                "submitted_date": row["timestamp"],
            })

        return results

    def check_pep(self, name: str) -> list[dict[str, Any]]:
        """Check if a name matches any PEP watchlist entries.

        Args:
            name: Name to check

        Returns:
            List of matching PEP entries
        """
        if self._pep_watchlist.empty:
            return []

        name_lower = name.lower()
        matches = self._pep_watchlist[
            self._pep_watchlist["name"].str.lower().str.contains(name_lower)
        ]

        return matches.to_dict("records")
