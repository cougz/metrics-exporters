"""Security middleware for LXC Metrics Exporter"""
import time
from typing import List, Optional
from fastapi import Request, Response, HTTPException
from fastapi.middleware.base import BaseHTTPMiddleware
from starlette.middleware.base import RequestResponseEndpoint
from logging_config import get_logger


logger = get_logger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to responses"""
    
    def __init__(self, app, trusted_hosts: Optional[List[str]] = None):
        super().__init__(app)
        self.trusted_hosts = trusted_hosts or []
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Add security headers to response"""
        # Validate trusted hosts if configured
        if self.trusted_hosts and request.client:
            host = request.headers.get("host", "")
            if host and not any(trusted in host for trusted in self.trusted_hosts):
                logger.warning(
                    "Untrusted host access attempt",
                    host=host,
                    client_ip=request.client.host,
                    event_type="security_violation"
                )
                raise HTTPException(status_code=403, detail="Forbidden: Untrusted host")
        
        # Process request
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        
        # Remove server version information
        response.headers.pop("server", None)
        
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple rate limiting middleware"""
    
    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.client_requests = {}
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Apply rate limiting"""
        if not request.client:
            return await call_next(request)
        
        client_ip = request.client.host
        current_time = time.time()
        
        # Clean up old entries
        cutoff_time = current_time - self.window_seconds
        self.client_requests = {
            ip: requests for ip, requests in self.client_requests.items()
            if any(req_time > cutoff_time for req_time in requests)
        }
        
        # Update client requests
        if client_ip not in self.client_requests:
            self.client_requests[client_ip] = []
        
        # Remove old requests for this client
        self.client_requests[client_ip] = [
            req_time for req_time in self.client_requests[client_ip]
            if req_time > cutoff_time
        ]
        
        # Check rate limit
        if len(self.client_requests[client_ip]) >= self.max_requests:
            logger.warning(
                "Rate limit exceeded",
                client_ip=client_ip,
                requests_count=len(self.client_requests[client_ip]),
                max_requests=self.max_requests,
                event_type="rate_limit_exceeded"
            )
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Try again later.",
                headers={"Retry-After": str(self.window_seconds)}
            )
        
        # Add current request
        self.client_requests[client_ip].append(current_time)
        
        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log HTTP requests"""
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Log HTTP requests"""
        start_time = time.time()
        
        # Log request
        logger.info(
            "HTTP request started",
            method=request.method,
            url=str(request.url),
            client_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            event_type="http_request_start"
        )
        
        # Process request
        try:
            response = await call_next(request)
            
            # Log response
            process_time = time.time() - start_time
            logger.info(
                "HTTP request completed",
                method=request.method,
                url=str(request.url),
                status_code=response.status_code,
                process_time_seconds=round(process_time, 3),
                client_ip=request.client.host if request.client else None,
                event_type="http_request_complete"
            )
            
            # Add processing time header
            response.headers["X-Process-Time"] = str(round(process_time, 3))
            
            return response
            
        except Exception as e:
            # Log error
            process_time = time.time() - start_time
            logger.error(
                "HTTP request failed",
                method=request.method,
                url=str(request.url),
                error=str(e),
                process_time_seconds=round(process_time, 3),
                client_ip=request.client.host if request.client else None,
                event_type="http_request_error",
                exc_info=True
            )
            raise


class HealthCheckMiddleware(BaseHTTPMiddleware):
    """Middleware to handle health checks efficiently"""
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Fast path for health checks"""
        # For health checks, skip other middleware processing if service is healthy
        if request.url.path in ["/health", "/ping"]:
            # Add minimal security headers for health checks
            response = await call_next(request)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers.pop("server", None)
            return response
        
        return await call_next(request)