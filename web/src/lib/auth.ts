import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";

const BASE = process.env.WHALETALE_API_URL ?? "http://127.0.0.1:8000";

/**
 * M6 interim: the operator signs in with their email and their operator API
 * token (issued by `create_operator_user` on the cloud). We verify by calling
 * the API once; a real password flow with server-issued tokens is a follow-up.
 */
export const { handlers, auth, signIn, signOut } = NextAuth({
  session: { strategy: "jwt" },
  pages: { signIn: "/sign-in" },
  providers: [
    Credentials({
      credentials: { email: {}, token: {} },
      async authorize(raw) {
        const email = String(raw?.email ?? "").trim();
        const token = String(raw?.token ?? "").trim();
        if (!email || !token) return null;
        const res = await fetch(`${BASE}/v1/sites`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) return null;
        return { id: email, email, apiToken: token };
      },
    }),
  ],
  callbacks: {
    jwt({ token, user }) {
      if (user?.apiToken) token.apiToken = user.apiToken;
      return token;
    },
    session({ session, token }) {
      if (typeof token.apiToken === "string") session.apiToken = token.apiToken;
      return session;
    },
  },
});
