import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Allow static assets, Next.js internals, and proxy endpoints
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon.ico") ||
    pathname.startsWith("/api") ||
    pathname.startsWith("/health")
  ) {
    return NextResponse.next();
  }

  const sessionCookie = request.cookies.get("session");
  const isAuthenticated = Boolean(sessionCookie?.value);

  // If user is already logged in and visits /login, redirect to /review
  if (pathname === "/login") {
    if (isAuthenticated) {
      return NextResponse.redirect(new URL("/review", request.url));
    }
    return NextResponse.next();
  }

  // If user is not authenticated and tries to access any dashboard page, redirect to /login
  if (!isAuthenticated) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("from", pathname);
    return NextResponse.redirect(loginUrl);
  }

  // If authenticated user visits root '/', redirect to /review
  if (pathname === "/") {
    return NextResponse.redirect(new URL("/review", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all request paths except for the ones starting with:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     */
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};

