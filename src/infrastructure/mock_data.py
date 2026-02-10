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

    def create_customer(self, customer_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new customer record.

        Args:
            customer_data: Customer data with fields: first_name, last_name, email,
                          phone, address, date_of_birth, nationality

        Returns:
            Created customer dict with generated ID
        """
        # Generate new customer ID
        if self._customers.empty:
            new_id = "C001"
        else:
            max_id = self._customers["id"].str.extract(r"C(\d+)").astype(int).max()[0]
            new_id = f"C{max_id + 1:03d}"

        customer = {
            "id": new_id,
            "first_name": customer_data.get("first_name", ""),
            "last_name": customer_data.get("last_name", ""),
            "email": customer_data.get("email", ""),
            "phone": customer_data.get("phone", ""),
            "address": customer_data.get("address", ""),
            "date_of_birth": customer_data.get("date_of_birth", ""),
            "nationality": customer_data.get("nationality", ""),
        }

        # Add to DataFrame
        self._customers = pd.concat(
            [self._customers, pd.DataFrame([customer])],
            ignore_index=True,
        )

        # Save to CSV
        self._save_csv("customers.csv", self._customers)

        return customer

    def create_account(
        self,
        customer_id: str,
        account_type: str = "current",
        initial_balance: float = 0.0,
    ) -> dict[str, Any]:
        """Create a new account for a customer.

        Args:
            customer_id: Customer ID
            account_type: Type of account (current, savings, business)
            initial_balance: Initial balance

        Returns:
            Created account dict
        """
        import random

        # Generate new account ID
        if self._accounts.empty:
            new_id = "A001"
        else:
            max_id = self._accounts["id"].str.extract(r"A(\d+)").astype(int).max()[0]
            new_id = f"A{max_id + 1:03d}"

        # Generate IBAN-like account number
        random_digits = "".join([str(random.randint(0, 9)) for _ in range(14)])
        account_number = f"IE29ZAVA9311{random_digits}"

        account = {
            "id": new_id,
            "customer_id": customer_id,
            "account_type": account_type,
            "account_number": account_number,
            "balance": str(initial_balance),
            "open_date": datetime.now().strftime("%Y-%m-%d"),
            "status": "pending_kyc",
        }

        # Add to DataFrame
        self._accounts = pd.concat(
            [self._accounts, pd.DataFrame([account])],
            ignore_index=True,
        )

        # Save to CSV
        self._save_csv("accounts.csv", self._accounts)

        return account

    def add_kyc_document(
        self,
        customer_id: str,
        doc_type: str,
        file_path: str,
        expiry_date: str = "",
    ) -> dict[str, Any]:
        """Add a KYC document record for a customer.

        Args:
            customer_id: Customer ID
            doc_type: Document type (passport, driving_license, utility_bill)
            file_path: Path where document is stored
            expiry_date: Document expiry date (optional)

        Returns:
            Created document record
        """
        # Generate new document ID
        if self._documents.empty:
            new_id = "D001"
        else:
            max_id = self._documents["id"].str.extract(r"D(\d+)").astype(int).max()[0]
            new_id = f"D{max_id + 1:03d}"

        document = {
            "id": new_id,
            "customer_id": customer_id,
            "doc_type": doc_type,
            "status": "pending",
            "file_path": file_path,
            "upload_date": datetime.now().strftime("%Y-%m-%d"),
            "expiry_date": expiry_date or "",
        }

        # Add to DataFrame
        self._documents = pd.concat(
            [self._documents, pd.DataFrame([document])],
            ignore_index=True,
        )

        # Save to CSV
        self._save_csv("kyc_documents.csv", self._documents)

        return document

    def _save_csv(self, filename: str, df: pd.DataFrame) -> None:
        """Save DataFrame to CSV file.

        Args:
            filename: Name of the CSV file
            df: DataFrame to save
        """
        filepath = self._data_dir / filename
        df.to_csv(filepath, index=False)
