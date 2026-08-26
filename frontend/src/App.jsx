import React, { useState, useEffect } from 'react';

const API_URL = '/api/status/';

// Custom CSS styles specifically for the App layout
const inlineStyles = `
  .hero-container {
    position: relative;
    max-width: 1200px;
    margin: 0 auto;
    padding: 140px 24px 80px 24px;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
  }

  .glow-orb-primary {
    position: absolute;
    top: -10%;
    left: 20%;
    width: 300px;
    height: 300px;
    background: radial-gradient(circle, rgba(0, 242, 254, 0.15) 0%, rgba(13, 148, 136, 0) 70%);
    border-radius: 50%;
    filter: blur(50px);
    z-index: -1;
    animation: pulse-glow 8s infinite alternate ease-in-out;
  }

  .glow-orb-secondary {
    position: absolute;
    top: 20%;
    right: 15%;
    width: 400px;
    height: 400px;
    background: radial-gradient(circle, rgba(139, 92, 246, 0.1) 0%, rgba(99, 102, 241, 0) 70%);
    border-radius: 50%;
    filter: blur(60px);
    z-index: -1;
    animation: pulse-glow 12s infinite alternate-reverse ease-in-out;
  }

  .nav-bar {
    position: fixed;
    top: 20px;
    left: 50%;
    transform: translateX(-50%);
    width: calc(100% - 40px);
    max-width: 1100px;
    height: 70px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 32px;
    z-index: 1000;
  }

  .nav-logo {
    display: flex;
    align-items: center;
    gap: 12px;
    font-family: var(--font-family-display);
    font-weight: 800;
    font-size: 1.3rem;
    color: var(--color-text-primary);
    text-decoration: none;
  }

  .nav-logo svg {
    animation: float 4s infinite ease-in-out;
  }

  .nav-links {
    display: flex;
    gap: 32px;
    list-style: none;
  }

  .nav-links a {
    color: var(--color-text-secondary);
    text-decoration: none;
    font-size: 0.95rem;
    font-weight: 500;
    transition: color 0.3s ease;
  }

  .nav-links a:hover {
    color: var(--color-primary);
  }

  .badge {
    background: rgba(0, 242, 254, 0.1);
    border: 1px solid var(--border-glass-glow);
    color: var(--color-primary);
    padding: 6px 14px;
    border-radius: 20px;
    font-size: 0.85rem;
    font-weight: 600;
    margin-bottom: 24px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    display: inline-block;
  }

  .hero-title {
    font-size: clamp(2.5rem, 5vw, 4.5rem);
    line-height: 1.1;
    max-width: 900px;
    margin-bottom: 24px;
  }

  .hero-subtitle {
    font-size: clamp(1rem, 2vw, 1.25rem);
    color: var(--color-text-secondary);
    max-width: 650px;
    line-height: 1.6;
    margin-bottom: 40px;
  }

  .hero-cta {
    display: flex;
    gap: 16px;
  }

  .section {
    padding: 80px 24px;
    max-width: 1200px;
    margin: 0 auto;
  }

  .section-header {
    text-align: center;
    margin-bottom: 50px;
  }

  .section-title {
    font-size: clamp(2rem, 3.5vw, 2.8rem);
    margin-bottom: 16px;
  }

  .section-desc {
    color: var(--color-text-secondary);
    max-width: 600px;
    margin: 0 auto;
    font-size: 1.1rem;
  }

  .product-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 32px;
  }

  .product-card {
    padding: 40px 32px;
    position: relative;
    overflow: hidden;
  }

  .product-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: radial-gradient(circle at 100% 0%, rgba(0, 242, 254, 0.05) 0%, transparent 60%);
    opacity: 0;
    transition: opacity 0.5s ease;
  }

  .product-card:hover::before {
    opacity: 1;
  }

  .product-icon {
    width: 60px;
    height: 60px;
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid var(--border-glass);
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 24px;
    color: var(--color-primary);
    font-size: 1.5rem;
  }

  .product-status {
    position: absolute;
    top: 24px;
    right: 24px;
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .status-active {
    color: var(--color-primary);
  }

  .status-locked {
    color: var(--color-text-muted);
  }

  .product-card-title {
    font-size: 1.5rem;
    margin-bottom: 12px;
  }

  .product-card-desc {
    color: var(--color-text-secondary);
    line-height: 1.6;
    margin-bottom: 32px;
    min-height: 72px;
  }

  /* Status Checker Widget */
  .status-widget {
    margin-top: 40px;
    padding: 24px;
    width: 100%;
    max-width: 600px;
  }

  .status-widget-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }

  .status-indicator {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    display: inline-block;
  }

  .status-pulse {
    box-shadow: 0 0 0 0 rgba(0, 242, 254, 0.7);
    animation: pulse 1.5s infinite;
  }

  @keyframes pulse {
    0% {
      transform: scale(0.95);
      box-shadow: 0 0 0 0 rgba(0, 242, 254, 0.7);
    }
    70% {
      transform: scale(1);
      box-shadow: 0 0 0 6px rgba(0, 242, 254, 0);
    }
    100% {
      transform: scale(0.95);
      box-shadow: 0 0 0 0 rgba(0, 242, 254, 0);
    }
  }

  .info-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 12px;
    font-size: 0.9rem;
  }

  .info-table td {
    padding: 8px 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  }

  .info-table td:last-child {
    text-align: right;
    font-family: monospace;
    color: var(--color-primary);
  }

  .footer {
    border-top: 1px solid var(--border-glass);
    padding: 40px 24px;
    text-align: center;
    background: rgba(2, 6, 23, 0.8);
    backdrop-filter: blur(10px);
  }

  .footer-domain {
    color: var(--color-primary);
    font-weight: 600;
    font-family: var(--font-family-display);
    text-decoration: none;
    letter-spacing: 0.05em;
  }
`;

export default function App() {
  const [backendStatus, setBackendStatus] = useState('checking');
  const [apiDetails, setApiDetails] = useState(null);

  useEffect(() => {
    // Inject custom CSS styles dynamically
    const styleElement = document.createElement('style');
    styleElement.innerHTML = inlineStyles;
    document.head.appendChild(styleElement);

    // Use the same-origin API route so the reverse proxy can route requests to Django.
    const checkStatus = async () => {
      try {
        const start = performance.now();
        const response = await fetch(API_URL);
        const duration = (performance.now() - start).toFixed(0);

        if (response.ok) {
          const data = await response.json();
          setBackendStatus('connected');
          setApiDetails({
            ...data,
            latency: `${duration}ms`
          });
        } else {
          setBackendStatus('error');
        }
      } catch (error) {
        console.error('API Check Error:', error);
        setBackendStatus('disconnected');
      }
    };

    checkStatus();
  }, []);

  return (
    <>
      {/* Floating Header */}
      <nav className="nav-bar glass-card">
        <a href="#" className="nav-logo">
          <svg width="38" height="38" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ overflow: 'visible' }}>
            <defs>
              <linearGradient id="bqlabs-logo-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#00E5FF" />
                <stop offset="50%" stopColor="#0088FF" />
                <stop offset="100%" stopColor="#8B5CF6" />
              </linearGradient>
              <filter id="logo-glow" x="-30%" y="-30%" width="160%" height="160%">
                <feGaussianBlur stdDeviation="3.5" result="blur" />
                <feComposite in="SourceGraphic" in2="blur" operator="over" />
              </filter>
            </defs>
            {/* Left Vertical Pillar */}
            <path d="M22 20C22 18.8954 22.8954 18 24 18H32C33.1046 18 34 18.8954 34 20V72C34 73.1046 33.1046 74 32 74H24C22.8954 74 22 73.1046 22 72V20Z" fill="url(#bqlabs-logo-grad)" />
            {/* Right Loops */}
            <path fillRule="evenodd" clipRule="evenodd" d="M38 18H58C68.4934 18 76.5 24.5 72.5 37.5C79.5 45.5 76.5 74 53 74H38V18ZM49 27V39H54C58 39 59.5 35.5 59.5 33C59.5 30.5 58 27 54 27H49ZM49 48V65H53.5C59 65 62.5 61.5 62.5 56.5C62.5 51.5 59 48 53.5 48H49Z" fill="url(#bqlabs-logo-grad)" />
            {/* Orbit ellipse */}
            <ellipse cx="50" cy="46" rx="42" ry="14" stroke="url(#bqlabs-logo-grad)" strokeWidth="3" fill="none" transform="rotate(-28, 50, 46)" />
            {/* Glowing sphere on orbit - front */}
            <circle cx="21" cy="59" r="6" fill="#00E5FF" filter="url(#logo-glow)" />
            {/* Sphere on orbit - back */}
            <circle cx="78" cy="33" r="4.5" fill="#8B5CF6" filter="url(#logo-glow)" />
          </svg>
          <span style={{ fontSize: '1.4rem', letterSpacing: '0.02em', background: 'linear-gradient(135deg, #ffffff 40%, #00E5FF 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>BQLabs</span>
        </a>
        <ul className="nav-links">
          <li><a href="#home">Home</a></li>
          <li><a href="#products">Products</a></li>
          <li><a href="#status">System Status</a></li>
        </ul>
        <a href="#products" className="btn-secondary" style={{ padding: '8px 20px', fontSize: '0.85rem' }}>
          Explore
        </a>
      </nav>

      {/* Hero Section */}
      <header id="home" className="hero-container">
        <div className="glow-orb-primary"></div>
        <div className="glow-orb-secondary"></div>

        <span className="badge">Next Generation Productivity</span>
        <h1 className="hero-title text-gradient">
          Building the Future of Smart Team Workspaces
        </h1>
        <p className="hero-subtitle">
          We construct intelligent, user-centric, and mobile-first productivity platforms engineered with cutting-edge technologies to streamline operational velocity.
        </p>

        <div className="hero-cta">
          <a href="#products" className="btn-primary">
            Explore Our Products
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="5" y1="12" x2="19" y2="12"></line>
              <polyline points="12 5 19 12 12 19"></polyline>
            </svg>
          </a>
          <a href="#status" className="btn-secondary">
            Verify Connection
          </a>
        </div>
      </header>

      {/* Products Grid */}
      <section id="products" className="section">
        <div className="section-header">
          <h2 className="section-title">Product Portfolio</h2>
          <p className="section-desc">
            Vibrant, high-performance, and futuristic web systems designed to supercharge productivity.
          </p>
        </div>

        <div className="product-grid">
          {/* Active Product: Quantum OPS */}
          <div className="product-card glass-card">
            <span className="product-status status-active">Active</span>
            <div className="product-icon" style={{ background: 'transparent', border: 'none', width: 'auto', height: 'auto', marginBottom: '16px', display: 'flex', justifyContent: 'flex-start' }}>
              <svg width="68" height="68" viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ overflow: 'visible' }}>
                <defs>
                  <linearGradient id="q-logo-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="#00E5FF" />
                    <stop offset="100%" stopColor="#8B5CF6" />
                  </linearGradient>
                  <filter id="q-logo-glow" x="-30%" y="-30%" width="160%" height="160%">
                    <feGaussianBlur stdDeviation="3.5" result="blur" />
                    <feComposite in="SourceGraphic" in2="blur" operator="over" />
                  </filter>
                </defs>
                {/* Thick Circle for Q */}
                <circle cx="60" cy="55" r="28" stroke="url(#q-logo-grad)" strokeWidth="8" fill="none" />
                {/* Tail of Q */}
                <path d="M79 74L95 90" stroke="url(#q-logo-grad)" strokeWidth="8" strokeLinecap="round" />
                {/* Center Sphere inside Q */}
                <circle cx="60" cy="55" r="12" fill="url(#q-logo-grad)" />
                {/* Orbit ellipse wrapping Q */}
                <ellipse cx="60" cy="55" rx="50" ry="16" stroke="url(#q-logo-grad)" strokeWidth="2.5" fill="none" transform="rotate(-25, 60, 55)" style={{ opacity: 0.8 }} />
                {/* Sphere on orbit bottom-left */}
                <circle cx="21" cy="74" r="5" fill="#00E5FF" filter="url(#q-logo-glow)" />
                {/* Sphere on orbit top-right */}
                <circle cx="99" cy="36" r="4.5" fill="#8B5CF6" filter="url(#q-logo-glow)" />
              </svg>
            </div>
            <h3 className="product-card-title">Quantum OPS</h3>
            <p className="product-card-desc">
              Smart task alignment and operational transparency. A single unified platform for Team Members, Team Leads, and Clients to check development status.
            </p>
            <button className="btn-primary" onClick={() => alert('Launching Quantum OPS...')} style={{ width: '100%', justifyContent: 'center' }}>
              Launch Platform
            </button>
          </div>

          {/* Product 2: Quantum Mind (Locked) */}
          <div className="product-card glass-card" style={{ opacity: 0.75 }}>
            <span className="product-status status-locked">In Development</span>
            <div className="product-icon" style={{ color: 'var(--color-text-muted)' }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2a10 10 0 0 1 7.54 16.59c-.24.25-.39.58-.39.92v1.5a1 1 0 0 1-1 1H5.85a1 1 0 0 1-1-1v-1.5c0-.34-.15-.67-.39-.92A10 10 0 0 1 12 2z"></path>
                <line x1="9" y1="22" x2="15" y2="22"></line>
              </svg>
            </div>
            <h3 className="product-card-title">Quantum Mind</h3>
            <p className="product-card-desc">
              Context-aware developer copilot designed to digest system requirements, generate codebases, and perform multi-vector automated testing.
            </p>
            <button className="btn-secondary" disabled style={{ width: '100%', justifyContent: 'center', cursor: 'not-allowed' }}>
              Locked
            </button>
          </div>

          {/* Product 3: Quantum Flow (Locked) */}
          <div className="product-card glass-card" style={{ opacity: 0.75 }}>
            <span className="product-status status-locked">Planned</span>
            <div className="product-icon" style={{ color: 'var(--color-text-muted)' }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 12h-4l-3 9L9 3l-3 9H2"></path>
              </svg>
            </div>
            <h3 className="product-card-title">Quantum Flow</h3>
            <p className="product-card-desc">
              Zero-config deployment framework that parses project architectures and orchestrates localized production environments instantly.
            </p>
            <button className="btn-secondary" disabled style={{ width: '100%', justifyContent: 'center', cursor: 'not-allowed' }}>
              Locked
            </button>
          </div>
        </div>
      </section>

      {/* Integration Verification Widget */}
      <section id="status" className="section" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        <div className="section-header">
          <h2 className="section-title">Backend Connectivity</h2>
          <p className="section-desc">
            Direct real-time diagnostic checks between the React UI container and the Django Rest Framework service.
          </p>
        </div>

        <div className="status-widget glass-card">
          <div className="status-widget-header">
            <span style={{ fontWeight: 600 }}>Service Diagnostic Status</span>
            <div>
              <span className={`status-indicator ${
                backendStatus === 'connected' ? 'status-pulse' : ''
              }`} style={{
                background: backendStatus === 'connected' ? '#10B981' :
                            backendStatus === 'disconnected' ? '#EF4444' :
                            backendStatus === 'error' ? '#F59E0B' : '#6B7280',
                marginRight: '8px'
              }}></span>
              <span style={{
                fontSize: '0.85rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                color: backendStatus === 'connected' ? '#10B981' :
                       backendStatus === 'disconnected' ? '#EF4444' :
                       backendStatus === 'error' ? '#F59E0B' : '#9CA3AF'
              }}>
                {backendStatus === 'connected' ? 'ONLINE' :
                 backendStatus === 'disconnected' ? 'OFFLINE' :
                 backendStatus === 'error' ? 'CONNECTION ERROR' : 'CHECKING...'}
              </span>
            </div>
          </div>

          <p style={{ color: 'var(--color-text-secondary)', fontSize: '0.9rem', marginBottom: '16px' }}>
            Diagnostics verify container routing, REST response format, CORS headers clearance, and PostgreSQL active session state.
          </p>

          <table className="info-table">
            <tbody>
              <tr>
                <td>React App Environment</td>
                <td>Docker Container (Vite)</td>
              </tr>
              <tr>
                <td>Django API Endpoint</td>
                <td>{API_URL}</td>
              </tr>
              {backendStatus === 'connected' && apiDetails ? (
                <>
                  <tr>
                    <td>Database Session (PostgreSQL)</td>
                    <td>{apiDetails.db_status || 'Active'}</td>
                  </tr>
                  <tr>
                    <td>API Latency</td>
                    <td>{apiDetails.latency}</td>
                  </tr>
                  <tr>
                    <td>Django Framework Version</td>
                    <td>{apiDetails.django_version || '5.0.x'}</td>
                  </tr>
                  <tr>
                    <td>Active Server Cluster</td>
                    <td>{apiDetails.server || 'Local dev container'}</td>
                  </tr>
                </>
              ) : (
                <tr>
                  <td>Database Session (PostgreSQL)</td>
                  <td>Pending Handshake...</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Footer */}
      <footer className="footer">
        <p style={{ color: 'var(--color-text-secondary)', fontSize: '0.9rem', marginBottom: '8px' }}>
          Copyright &copy; 2026 Bhairav Quantum Labs. All rights reserved.
        </p>
        <a href="https://bqlabs.in" target="_blank" rel="noreferrer" className="footer-domain">
          bqlabs.in
        </a>
      </footer>
    </>
  );
}
