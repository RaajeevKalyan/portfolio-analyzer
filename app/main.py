"""
Flask Application Entry Point
"""
from flask import Flask, render_template_string
from app.config import get_config
import logging
from logging.handlers import RotatingFileHandler
import os


def create_app():
    """Application factory"""
    app = Flask(__name__)
    
    # Load configuration
    config = get_config()
    app.config.from_object(config)
    
    # Validate configuration
    config.validate()
    
    # Setup logging
    setup_logging(app)
    
    # Register routes
    register_routes(app)
    
    # Create necessary directories
    os.makedirs('/app/data', exist_ok=True)
    os.makedirs('/app/logs', exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    app.logger.info('Portfolio Risk Analyzer started')
    
    return app


def setup_logging(app):
    """Configure application logging"""
    if not app.debug:
        # File handler
        file_handler = RotatingFileHandler(
            app.config['LOG_FILE'],
            maxBytes=10485760,  # 10MB
            backupCount=10
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)


def register_routes(app):
    """Register application routes"""
    
    @app.route('/')
    def index():
        """Home page - temporary hello world"""
        html = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Portfolio Risk Analyzer</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
            <style>
                body {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
                .welcome-card {
                    background: white;
                    border-radius: 20px;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    padding: 3rem;
                    max-width: 600px;
                    text-align: center;
                }
                .broker-icons {
                    display: flex;
                    justify-content: center;
                    gap: 1.5rem;
                    margin: 2rem 0;
                }
                .broker-icon {
                    font-size: 2rem;
                }
                .fa-building-columns { color: #CC0000; }
                .fa-chart-line { color: #00783E; }
                .fa-chart-simple { color: #5B21B6; }
                .fa-arrow-trend-up { color: #00C805; }
                .fa-landmark { color: #00A0DC; }
            </style>
        </head>
        <body>
            <div class="welcome-card">
                <h1 class="mb-4">
                    <i class="fas fa-chart-pie text-primary"></i>
                    Portfolio Risk Analyzer
                </h1>
                <p class="lead text-muted">
                    Aggregate your investments across multiple brokers and analyze risk concentrations.
                </p>
                
                <div class="broker-icons">
                    <i class="fas fa-building-columns broker-icon" title="Merrill Lynch"></i>
                    <i class="fas fa-chart-line broker-icon" title="Fidelity"></i>
                    <i class="fas fa-chart-simple broker-icon" title="Webull"></i>
                    <i class="fas fa-arrow-trend-up broker-icon" title="Robinhood"></i>
                    <i class="fas fa-landmark broker-icon" title="Schwab"></i>
                </div>
                
                <div class="alert alert-success" role="alert">
                    <i class="fas fa-check-circle"></i>
                    <strong>Application running successfully!</strong>
                </div>
                
                <p class="text-muted small">
                    <i class="fas fa-lock"></i>
                    Secure HTTPS connection established<br>
                    <i class="fas fa-server"></i>
                    Flask + Gunicorn + nginx
                </p>
                
                <div class="mt-4 pt-4 border-top">
                    <p class="text-muted small mb-0">
                        <strong>Next Steps:</strong><br>
                        Database setup → CSV parsers → Dashboard
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        return render_template_string(html)
    
    @app.route('/health')
    def health():
        """Health check endpoint for Docker"""
        return {'status': 'healthy', 'service': 'portfolio-analyzer'}, 200


# Create application instance
app = create_app()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)