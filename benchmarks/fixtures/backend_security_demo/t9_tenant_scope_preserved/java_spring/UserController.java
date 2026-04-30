package com.example.projectapi.controller;

import com.example.projectapi.model.User;
import com.example.projectapi.model.Project;
import com.example.projectapi.repository.UserRepository;
import com.example.projectapi.repository.ProjectRepository;
import com.example.projectapi.service.ExportService;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import javax.validation.Valid;
import java.security.Principal;
import java.util.List;

/**
 * User and Project management controller.
 * All endpoints require authentication. Admin endpoints require ADMIN role.
 * All queries are scoped to the authenticated user's tenant.
 */
@RestController
@RequestMapping("/api")
public class UserController {

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private ProjectRepository projectRepository;

    @Autowired
    private ExportService exportService;

    /**
     * List users within the authenticated user's tenant.
     */
    @GetMapping("/users")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Page<User>> listUsers(
            @AuthenticationPrincipal Principal principal,
            Pageable pageable) {
        String tenantId = getTenantId(principal);
        Page<User> users = userRepository.findByTenantId(tenantId, pageable);
        return ResponseEntity.ok(users);
    }

    /**
     * List projects within tenant scope.
     */
    @GetMapping("/projects")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<List<Project>> listProjects(
            @AuthenticationPrincipal Principal principal) {
        String tenantId = getTenantId(principal);
        List<Project> projects = projectRepository.findByTenantId(tenantId);
        return ResponseEntity.ok(projects);
    }

    /**
     * Get a specific project within tenant scope.
     */
    @GetMapping("/projects/{projectId}")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Project> getProject(
            @PathVariable String projectId,
            @AuthenticationPrincipal Principal principal) {
        String tenantId = getTenantId(principal);
        Project project = projectRepository.findByIdAndTenantId(projectId, tenantId);
        if (project == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(project);
    }

    /**
     * Create a new project within the user's tenant.
     */
    @PostMapping("/projects")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Project> createProject(
            @Valid @RequestBody Project project,
            @AuthenticationPrincipal Principal principal) {
        String tenantId = getTenantId(principal);
        project.setTenantId(tenantId);
        project.setOwnerId(principal.getName());
        Project saved = projectRepository.save(project);
        return ResponseEntity.ok(saved);
    }

    /**
     * Delete a user (admin only, within tenant).
     */
    @DeleteMapping("/users/{userId}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Void> deleteUser(
            @PathVariable String userId,
            @AuthenticationPrincipal Principal principal) {
        String tenantId = getTenantId(principal);
        User user = userRepository.findByIdAndTenantId(userId, tenantId);
        if (user == null) {
            return ResponseEntity.notFound().build();
        }
        userRepository.delete(user);
        return ResponseEntity.ok().build();
    }

    /**
     * Export user list (admin only, within tenant).
     */
    @GetMapping("/admin/export-users")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<List<User>> exportUsers(
            @AuthenticationPrincipal Principal principal) {
        String tenantId = getTenantId(principal);
        List<User> users = userRepository.findByTenantId(tenantId);
        return ResponseEntity.ok(users);
    }

    /**
     * Update user role (admin only).
     */
    @PutMapping("/users/{userId}/role")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<User> updateUserRole(
            @PathVariable String userId,
            @RequestBody @Valid User roleUpdate,
            @AuthenticationPrincipal Principal principal) {
        String tenantId = getTenantId(principal);
        User user = userRepository.findByIdAndTenantId(userId, tenantId);
        if (user == null) {
            return ResponseEntity.notFound().build();
        }
        user.setRole(roleUpdate.getRole());
        userRepository.save(user);
        return ResponseEntity.ok(user);
    }

    // --- Helper ---

    private String getTenantId(Principal principal) {
        // In real app, extract from JWT claims or user profile
        return principal.getName().split("@")[0];
    }
}
