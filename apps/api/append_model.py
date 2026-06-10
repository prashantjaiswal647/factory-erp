class PurchaseRateHistory(TenantMixin, Base):
    __tablename__ = "purchase_rate_history"

    id = Column(Integer, primary_key=True, index=True)
    item_category = Column(String(50), nullable=False)
    identifier = Column(String(255), nullable=False)  # size or packaging name
    rate = Column(Numeric(14, 2), nullable=False)
    purchase_date = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class RecoveryFollowup(TenantMixin, Base):
    """P4.11: Track recovery follow-up actions per customer.

    One row per customer action attempt. Owner/Sub-Owner can view suggestions;
    only Owner can mark final follow-up action for financially sensitive data.

    Status lifecycle:
      suggested (default) -> copied / skipped / followup_done / snoozed
    """
    __tablename__ = "recovery_followups"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    outstanding_bill_id = Column(Integer, ForeignKey("outstanding_bills.id"), nullable=True)
    suggested_amount_paise = Column(BigInteger, nullable=False, default=0)
    due_days = Column(Integer, nullable=False, default=0)
    status = Column(String(30), nullable=False, default="suggested", server_default="suggested",
                    index=True)  # suggested, copied, skipped, followup_done, snoozed
    snoozed_until = Column(DateTime(timezone=True), nullable=True)
    last_action_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    customer = relationship("Customer", backref="recovery_followups")
    created_by = relationship("User", backref="recovery_followups")

    __table_args__ = (
        Index("ix_recovery_followups_factory_status", "factory_id", "status"),
    )