"""
This file contains celery tasks for sending email
"""
import time
from django.conf import settings
from django.core import mail

from celery.task import task  # pylint: disable=no-name-in-module, import-error
from celery.utils.log import get_task_logger  # pylint: disable=no-name-in-module, import-error

log = get_task_logger(__name__)


@task()
def send_activation_email(user, subject, message, from_address):
    """
    Sending an activation email to the users.
    """
    max_retries = settings.RETRY_ACTIVATION_EMAIL_MAX_ATTEMPTS
    retries = 0
    dest_addr = user.email
    while retries < max_retries:
        try:
            if settings.FEATURES.get('REROUTE_ACTIVATION_EMAIL'):
                dest_addr = settings.FEATURES['REROUTE_ACTIVATION_EMAIL']
                message = ("Activation for %s (%s): %s\n" % (user, user.email, user.profile.name) +
                           '-' * 80 + '\n\n' + message)
                mail.send_mail(subject, message, from_address, [dest_addr], fail_silently=False)
            else:
                user.email_user(subject, message, from_address)
            # Log that the Activation Email has been sent to user without an exception
            log.info("Activataion Email has been sent to User {user_email}".format(
                user_email=dest_addr
            ))
            break
        except Exception:  # pylint: disable=broad-except
            retries += 1
            if retries >= max_retries:
                log.error(
                    'Unable to send activation email to user from "%s" to "%s"',
                    from_address,
                    dest_addr,
                    exc_info=True
                )
                raise Exception
            else:
                log.info('Retrying sending email to user {dest_addr}, attempt # {attempt} of {max_attempts}'. format(
                    dest_addr=dest_addr,
                    attempt=retries,
                    max_attempts=max_retries
                ))
                time.sleep(settings.RETRY_ACTIVATION_EMAIL_TIMEOUT)
