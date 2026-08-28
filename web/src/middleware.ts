import { auth } from "@/lib/auth";

export default auth((req) => {
  const signedIn = !!req.auth?.apiToken;
  const { pathname } = req.nextUrl;
  const onSignIn = pathname === "/sign-in";
  if (!signedIn && !onSignIn) {
    const url = new URL("/sign-in", req.nextUrl);
    url.searchParams.set("next", pathname);
    return Response.redirect(url);
  }
  if (signedIn && onSignIn) {
    return Response.redirect(new URL("/", req.nextUrl));
  }
});

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api/auth).*)"],
};
