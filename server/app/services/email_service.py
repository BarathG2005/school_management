"""
app/services/email_service.py
Email service using SendGrid
"""
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class EmailService:
    """Email service for sending transactional emails"""
    
    def __init__(self):
        if settings.SENDGRID_API_KEY:
            self.sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        else:
            self.sg = None
            logger.warning("SendGrid API key not configured. Emails will be logged only.")
        
        self.from_email = settings.FROM_EMAIL
        self.from_name = settings.FROM_NAME
    
    async def send_email(self, to_email: str, subject: str, html_content: str):
        """
        Send email via SendGrid
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML content of email
        
        Returns:
            bool: True if sent successfully, False otherwise
        """
        if not self.sg:
            logger.info(f"[EMAIL] To: {to_email} | Subject: {subject}")
            logger.debug(f"[EMAIL] Content: {html_content}")
            return True
        
        try:
            message = Mail(
                from_email=(self.from_email, self.from_name),
                to_emails=to_email,
                subject=subject,
                html_content=html_content
            )
            
            response = self.sg.send(message)
            logger.info(f"Email sent to {to_email}: {response.status_code}")
            return True
            
        except Exception as e:
            logger.error(f"Email send failed to {to_email}: {e}")
            return False
    
    async def send_bulk_email(self, recipients: list, subject: str, html_content: str):
        """
        Send email to multiple recipients
        
        Args:
            recipients: List of email addresses
            subject: Email subject
            html_content: HTML content of email
        
        Returns:
            dict: Summary of sent emails
        """
        sent_count = 0
        failed_count = 0
        
        for email in recipients:
            success = await self.send_email(email, subject, html_content)
            if success:
                sent_count += 1
            else:
                failed_count += 1
        
        return {
            "total": len(recipients),
            "sent": sent_count,
            "failed": failed_count
        }
    
    async def send_welcome_email(self, to_email: str, name: str, role: str, temporary_password: str):
        """Send welcome email to new user"""
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #333;">Welcome to {settings.PROJECT_NAME}!</h2>
            <p>Dear {name},</p>
            <p>Your account has been created successfully.</p>
            <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p><strong>Role:</strong> {role.title()}</p>
                <p><strong>Email:</strong> {to_email}</p>
                <p><strong>Temporary Password:</strong> <code>{temporary_password}</code></p>
            </div>
            <p><strong>Important:</strong> Please change your password immediately after your first login.</p>
            <p>If you have any questions, please contact the administrator.</p>
            <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
            <p style="color: #666; font-size: 12px;">
                This is an automated email from {settings.PROJECT_NAME}. Please do not reply.
            </p>
        </div>
        """
        return await self.send_email(to_email, f"Welcome to {settings.PROJECT_NAME}", html_content)
    
    async def send_password_reset_email(self, to_email: str, name: str, reset_token: str):
        """Send password reset email"""
        # In production, this would be a link to your frontend
        reset_link = f"https://yourschool.com/reset-password?token={reset_token}"
        
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #333;">Password Reset Request</h2>
            <p>Dear {name},</p>
            <p>We received a request to reset your password. Click the button below to reset it:</p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{reset_link}" style="background-color: #4CAF50; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                    Reset Password
                </a>
            </div>
            <p>If you didn't request a password reset, please ignore this email.</p>
            <p><strong>This link will expire in 1 hour.</strong></p>
            <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
            <p style="color: #666; font-size: 12px;">
                If the button doesn't work, copy and paste this link: {reset_link}
            </p>
        </div>
        """
        return await self.send_email(to_email, "Password Reset Request", html_content)