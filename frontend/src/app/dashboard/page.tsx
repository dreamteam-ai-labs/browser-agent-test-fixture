"use client";

import { useEffect, useState } from "react";
import Layout from "@/components/Layout";
import api from "@/lib/api";

interface UserInfo {
  id: number;
  email: string;
  display_name: string;
}

export default function DashboardPage() {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [projectCount, setProjectCount] = useState(0);
  const [taskCount, setTaskCount] = useState(0);

  useEffect(() => {
    api.get("/api/auth/me").then((res) => setUser(res.data));
    api.get("/api/projects").then((res) => setProjectCount(res.data.length));
    api.get("/api/tasks").then((res) => setTaskCount(res.data.length));
  }, []);

  return (
    <Layout>
      <div className="max-w-4xl">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Dashboard</h1>
        {user && (
          <p className="text-gray-600 mb-8">Welcome back, {user.display_name}!</p>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-white p-6 rounded-xl border border-gray-200">
            <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide">Projects</h3>
            <p className="text-3xl font-bold text-gray-900 mt-2">{projectCount}</p>
          </div>
          <div className="bg-white p-6 rounded-xl border border-gray-200">
            <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide">Tasks</h3>
            <p className="text-3xl font-bold text-gray-900 mt-2">{taskCount}</p>
          </div>
        </div>
      </div>
    </Layout>
  );
}
