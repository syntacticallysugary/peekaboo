<template>
  <nav class="navbar">
    <span class="logo">
      <span class="logo-accent">peekaboo</span><span class="logo-muted">.ai</span>
    </span>
    <div class="nav-links">
      <RouterLink to="/"        class="nav-link" exact-active-class="nav-link-active">Dashboard</RouterLink>
      <RouterLink to="/events"  class="nav-link" active-class="nav-link-active">Events</RouterLink>
      <RouterLink to="/persons" class="nav-link" active-class="nav-link-active">Persons</RouterLink>
      <RouterLink to="/settings" class="nav-link" active-class="nav-link-active">Settings</RouterLink>
    </div>
  </nav>

  <main class="main-content">
    <RouterView />
  </main>
</template>

<style scoped>
.navbar {
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(15, 23, 42, 0.9);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--color-border);
  padding: 1.1rem 2.5rem;
  display: flex;
  align-items: center;
  gap: 2.5rem;
}

.logo {
  font-family: var(--font-mono);
  font-size: 0.9rem;
  letter-spacing: 0.04em;
}
.logo-accent { color: var(--color-accent); }
.logo-muted  { color: var(--color-muted); }

.nav-links {
  display: flex;
  gap: 2rem;
  margin-left: 1rem;
}

.nav-link {
  font-size: 0.875rem;
  color: var(--color-muted);
  text-decoration: none;
  transition: color 0.2s;
}
.nav-link:hover     { color: var(--color-text); }
.nav-link-active    { color: var(--color-accent); }

.main-content {
  max-width: 1100px;
  margin: 0 auto;
  padding: 3rem 2.5rem;
}
</style>
