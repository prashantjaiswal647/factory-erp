-- Replace the phone number below before running.
UPDATE factories AS f
SET
    trial_start_date = NOW(),
    trial_end_date = NOW() + INTERVAL '30 days',
    subscription_status = 'trial'
FROM users AS u
WHERE u.factory_id = f.id
  AND u.phone_number = '+910000000000'
RETURNING f.id AS factory_id, f.trial_end_date, f.subscription_status;
