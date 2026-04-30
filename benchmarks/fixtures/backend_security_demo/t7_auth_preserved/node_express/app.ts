import express from 'express';
import cors from 'cors';
import jwt from 'jsonwebtoken';
import cookieParser from 'cookie-parser';

const app = express();
const router = express.Router();

// --- Security Config ---
app.use(cors({
  origin: ['https://app.example.com', 'https://admin.example.com'],
  credentials: true,
}));

app.use(cookieParser());
app.use(express.json());

app.use(express.session({
  secret: process.env.SESSION_SECRET!,
  cookie: { secure: true, httpOnly: true, sameSite: 'strict' },
}));

// --- Auth Middleware ---
function authMiddleware(req: any, res: any, next: any) {
  const token = req.headers.authorization?.replace('Bearer ', '');
  if (!token) {
    return res.status(401).json({ error: 'No token provided' });
  }
  try {
    const decoded = jwt.verify(token, process.env.JWT_SECRET!);
    req.user = decoded;
    next();
  } catch (err) {
    return res.status(401).json({ error: 'Invalid token' });
  }
}

function requireAdmin(req: any, res: any, next: any) {
  if (req.user.role !== 'admin') {
    return res.status(403).json({ error: 'Admin access required' });
  }
  next();
}

// Apply auth to all API routes
app.use('/api', authMiddleware);

// --- API Routes ---

router.get('/users', async (req: any, res: any) => {
  const tenantId = req.user.tenantId;
  const page = parseInt(req.query.page || '1');
  const size = parseInt(req.query.size || '20');
  const users = await db.users.find({
    where: { tenant_id: tenantId },
    skip: (page - 1) * size,
    take: size,
  });
  res.json({ users, page, size });
});

router.get('/projects', async (req: any, res: any) => {
  const tenantId = req.user.tenantId;
  const projects = await db.projects.find({
    where: { tenant_id: tenantId },
  });
  res.json({ projects });
});

router.get('/projects/:projectId', async (req: any, res: any) => {
  const tenantId = req.user.tenantId;
  const project = await db.projects.findOne({
    where: { id: req.params.projectId, tenant_id: tenantId },
  });
  if (!project) {
    return res.status(404).json({ error: 'Project not found' });
  }
  res.json(project);
});

router.post('/projects', async (req: any, res: any) => {
  const tenantId = req.user.tenantId;
  const project = await db.projects.create({
    ...req.body,
    tenant_id: tenantId,
    owner_id: req.user.id,
  });
  res.json(project);
});

router.delete('/users/:userId', requireAdmin, async (req: any, res: any) => {
  const tenantId = req.user.tenantId;
  const user = await db.users.findOne({
    where: { id: req.params.userId, tenant_id: tenantId },
  });
  if (!user) {
    return res.status(404).json({ error: 'User not found' });
  }
  await db.users.delete(user.id);
  res.json({ status: 'deleted' });
});

router.get('/admin/export-users', requireAdmin, async (req: any, res: any) => {
  const tenantId = req.user.tenantId;
  const users = await db.users.find({
    where: { tenant_id: tenantId },
  });
  res.json({ users, count: users.length });
});

router.put('/users/:userId/role', requireAdmin, async (req: any, res: any) => {
  const tenantId = req.user.tenantId;
  const user = await db.users.findOne({
    where: { id: req.params.userId, tenant_id: tenantId },
  });
  if (!user) {
    return res.status(404).json({ error: 'User not found' });
  }
  user.role = req.body.role;  // NOTE: role comes from admin, not from unverified user
  await db.users.save(user);
  res.json(user);
});

app.use('/api', router);

// --- Simulated DB ---
const db: any = {
  users: { find: async () => [], findOne: async () => null, create: async (d: any) => d, delete: async () => {}, save: async (d: any) => d },
  projects: { find: async () => [], findOne: async () => null, create: async (d: any) => d },
};

app.listen(3000, () => console.log('Server running on port 3000'));
