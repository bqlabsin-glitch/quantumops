# Workspace Rules

## Security, Scalability, and Performance
* **Security is the Highest Priority**:
  * Never commit secrets, passwords, API keys, or `.env` files to git.
  * Ensure all input is validated and sanitized to prevent SQL injection, XSS, and other common web vulnerabilities.
  * Implement proper authentication and authorization checks for all backend endpoints.
  * Enable CORS headers selectively; avoid using wide-open wildcards (`*`) in production configurations.
* **Scalability**:
  * Write efficient queries in Django using `select_related` and `prefetch_related` where appropriate to avoid the N+1 query problem.
  * Structure React state management efficiently to prevent unnecessary re-renders.
  * Utilize caching layer (Redis) for expensive queries or heavy computations where suitable.
* **High Performance**:
  * Keep frontend bundle sizes small.
  * Minimize API payload sizes.
  * Ensure pages render quickly and are fully responsive on all device sizes.
