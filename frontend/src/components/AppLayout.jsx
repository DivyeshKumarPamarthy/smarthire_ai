import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

/**
 * Each role is one scrolling page; these are the sections within it, in order.
 * The first item of each pair is the section's DOM id and URL hash.
 */
export const SECTIONS = {
  candidate: [
    ['overview', 'Overview'],
    ['resume', 'Resume'],
    ['interview', 'Interview'],
    ['history', 'History'],
    ['notifications', 'Alerts'],
    ['analytics', 'Analytics'],
    ['report', 'Report'],
    ['settings', 'Settings'],
  ],
  recruiter: [
    ['overview', 'Overview'],
    ['candidates', 'Candidates'],
    ['insights', 'Insights'],
    ['leaderboard', 'Leaderboard'],
    ['analytics', 'Analytics'],
    ['compare', 'Compare'],
    ['templates', 'Templates'],
    ['sessions', 'Sessions'],
    ['alerts', 'Alerts'],
    ['report', 'Report'],
  ],
  admin: [
    ['overview', 'Overview'],
    ['users', 'Users'],
    ['leaderboard', 'Leaderboard'],
    ['tickets', 'Tickets'],
    ['api', 'API'],
    ['activity', 'Activity'],
    ['alerts', 'Alerts'],
    ['ai', 'AI'],
    ['settings', 'Settings'],
  ],
};

export default function AppLayout({ children }) {
  const { user, role, logout } = useAuth();
  const navigate = useNavigate();
  const sections = SECTIONS[role] ?? [];
  const [active, setActive] = useState(sections[0]?.[0]);

  // Highlight whichever section is currently nearest the top of the viewport.
  useEffect(() => {
    const elements = sections
      .map(([id]) => document.getElementById(id))
      .filter(Boolean);
    if (elements.length === 0) return undefined;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: '-76px 0px -55% 0px' }
    );

    elements.forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [role]);

  // Honour a #hash on first load (e.g. /candidate#analytics).
  useEffect(() => {
    const id = window.location.hash.slice(1);
    if (!id) return;
    const target = document.getElementById(id);
    if (target) requestAnimationFrame(() => target.scrollIntoView());
  }, [role]);

  const goTo = (id) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    window.history.replaceState(null, '', `#${id}`);
  };

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  return (
    <>
      <header className="topbar">
        <Link to="/" className="brand">
          SmartHire<span>_AI</span>
        </Link>

        <nav className="nav">
          {sections.map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={id === active ? 'active' : undefined}
              onClick={() => goTo(id)}
            >
              {label}
            </button>
          ))}
        </nav>

        <div className="topbar-end">
          <span className="avatar" title={user?.name}>
            {user?.initials ?? '--'}
          </span>
          <button className="btn" onClick={handleLogout}>
            Log out
          </button>
        </div>
      </header>

      <main className="container">{children}</main>
    </>
  );
}
