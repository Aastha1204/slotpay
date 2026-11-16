-- Presenter timeline needs a stable order for events written in one transaction.
alter table audit_event alter column created_at set default clock_timestamp();
