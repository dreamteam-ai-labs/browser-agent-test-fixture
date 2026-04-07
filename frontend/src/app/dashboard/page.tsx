"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Layout from "@/components/Layout";
import api from "@/lib/api";

interface UserInfo {
  id: number;
  email: string;
  name: string;
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
          <p className="text-gray-600 mb-8">Welcome back, {user.name}!</p>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <div className="bg-white p-6 rounded-xl border border-gray-200">
            <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide">Projects</h3>
            <p className="text-3xl font-bold text-gray-900 mt-2">{projectCount}</p>
            <Link href="/projects" className="mt-4 inline-block text-sm text-blue-600 hover:text-blue-800">
              View all projects &rarr;
            </Link>
          </div>
          <div className="bg-white p-6 rounded-xl border border-gray-200">
            <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide">Tasks</h3>
            <p className="text-3xl font-bold text-gray-900 mt-2">{taskCount}</p>
            <Link href="/tasks" className="mt-4 inline-block text-sm text-blue-600 hover:text-blue-800">
              View all tasks &rarr;
            </Link>
          </div>
        </div>

        <div className="flex gap-4">
          <Link
            href="/projects"
            className="px-4 py-2 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition-colors"
          >
            Go to Projects
          </Link>
          <Link
            href="/tasks"
            className="px-4 py-2 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition-colors"
          >
            Go to Tasks
          </Link>
        </div>
      </div>
    </Layout>
  );
}
