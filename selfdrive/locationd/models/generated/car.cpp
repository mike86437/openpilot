#include "car.h"

namespace {
#define DIM 9
#define EDIM 9
#define MEDIM 9
typedef void (*Hfun)(double *, double *, double *);

double mass;

void set_mass(double x){ mass = x;}

double rotational_inertia;

void set_rotational_inertia(double x){ rotational_inertia = x;}

double center_to_front;

void set_center_to_front(double x){ center_to_front = x;}

double center_to_rear;

void set_center_to_rear(double x){ center_to_rear = x;}

double stiffness_front;

void set_stiffness_front(double x){ stiffness_front = x;}

double stiffness_rear;

void set_stiffness_rear(double x){ stiffness_rear = x;}
const static double MAHA_THRESH_25 = 3.8414588206941227;
const static double MAHA_THRESH_24 = 5.991464547107981;
const static double MAHA_THRESH_30 = 3.8414588206941227;
const static double MAHA_THRESH_26 = 3.8414588206941227;
const static double MAHA_THRESH_27 = 3.8414588206941227;
const static double MAHA_THRESH_29 = 3.8414588206941227;
const static double MAHA_THRESH_28 = 3.8414588206941227;
const static double MAHA_THRESH_31 = 3.8414588206941227;

/******************************************************************************
 *                       Code generated with SymPy 1.12                       *
 *                                                                            *
 *              See http://www.sympy.org/ for more information.               *
 *                                                                            *
 *                         This file is part of 'ekf'                         *
 ******************************************************************************/
void err_fun(double *nom_x, double *delta_x, double *out_300495555088403105) {
   out_300495555088403105[0] = delta_x[0] + nom_x[0];
   out_300495555088403105[1] = delta_x[1] + nom_x[1];
   out_300495555088403105[2] = delta_x[2] + nom_x[2];
   out_300495555088403105[3] = delta_x[3] + nom_x[3];
   out_300495555088403105[4] = delta_x[4] + nom_x[4];
   out_300495555088403105[5] = delta_x[5] + nom_x[5];
   out_300495555088403105[6] = delta_x[6] + nom_x[6];
   out_300495555088403105[7] = delta_x[7] + nom_x[7];
   out_300495555088403105[8] = delta_x[8] + nom_x[8];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_606621225230243076) {
   out_606621225230243076[0] = -nom_x[0] + true_x[0];
   out_606621225230243076[1] = -nom_x[1] + true_x[1];
   out_606621225230243076[2] = -nom_x[2] + true_x[2];
   out_606621225230243076[3] = -nom_x[3] + true_x[3];
   out_606621225230243076[4] = -nom_x[4] + true_x[4];
   out_606621225230243076[5] = -nom_x[5] + true_x[5];
   out_606621225230243076[6] = -nom_x[6] + true_x[6];
   out_606621225230243076[7] = -nom_x[7] + true_x[7];
   out_606621225230243076[8] = -nom_x[8] + true_x[8];
}
void H_mod_fun(double *state, double *out_9063386925137587863) {
   out_9063386925137587863[0] = 1.0;
   out_9063386925137587863[1] = 0;
   out_9063386925137587863[2] = 0;
   out_9063386925137587863[3] = 0;
   out_9063386925137587863[4] = 0;
   out_9063386925137587863[5] = 0;
   out_9063386925137587863[6] = 0;
   out_9063386925137587863[7] = 0;
   out_9063386925137587863[8] = 0;
   out_9063386925137587863[9] = 0;
   out_9063386925137587863[10] = 1.0;
   out_9063386925137587863[11] = 0;
   out_9063386925137587863[12] = 0;
   out_9063386925137587863[13] = 0;
   out_9063386925137587863[14] = 0;
   out_9063386925137587863[15] = 0;
   out_9063386925137587863[16] = 0;
   out_9063386925137587863[17] = 0;
   out_9063386925137587863[18] = 0;
   out_9063386925137587863[19] = 0;
   out_9063386925137587863[20] = 1.0;
   out_9063386925137587863[21] = 0;
   out_9063386925137587863[22] = 0;
   out_9063386925137587863[23] = 0;
   out_9063386925137587863[24] = 0;
   out_9063386925137587863[25] = 0;
   out_9063386925137587863[26] = 0;
   out_9063386925137587863[27] = 0;
   out_9063386925137587863[28] = 0;
   out_9063386925137587863[29] = 0;
   out_9063386925137587863[30] = 1.0;
   out_9063386925137587863[31] = 0;
   out_9063386925137587863[32] = 0;
   out_9063386925137587863[33] = 0;
   out_9063386925137587863[34] = 0;
   out_9063386925137587863[35] = 0;
   out_9063386925137587863[36] = 0;
   out_9063386925137587863[37] = 0;
   out_9063386925137587863[38] = 0;
   out_9063386925137587863[39] = 0;
   out_9063386925137587863[40] = 1.0;
   out_9063386925137587863[41] = 0;
   out_9063386925137587863[42] = 0;
   out_9063386925137587863[43] = 0;
   out_9063386925137587863[44] = 0;
   out_9063386925137587863[45] = 0;
   out_9063386925137587863[46] = 0;
   out_9063386925137587863[47] = 0;
   out_9063386925137587863[48] = 0;
   out_9063386925137587863[49] = 0;
   out_9063386925137587863[50] = 1.0;
   out_9063386925137587863[51] = 0;
   out_9063386925137587863[52] = 0;
   out_9063386925137587863[53] = 0;
   out_9063386925137587863[54] = 0;
   out_9063386925137587863[55] = 0;
   out_9063386925137587863[56] = 0;
   out_9063386925137587863[57] = 0;
   out_9063386925137587863[58] = 0;
   out_9063386925137587863[59] = 0;
   out_9063386925137587863[60] = 1.0;
   out_9063386925137587863[61] = 0;
   out_9063386925137587863[62] = 0;
   out_9063386925137587863[63] = 0;
   out_9063386925137587863[64] = 0;
   out_9063386925137587863[65] = 0;
   out_9063386925137587863[66] = 0;
   out_9063386925137587863[67] = 0;
   out_9063386925137587863[68] = 0;
   out_9063386925137587863[69] = 0;
   out_9063386925137587863[70] = 1.0;
   out_9063386925137587863[71] = 0;
   out_9063386925137587863[72] = 0;
   out_9063386925137587863[73] = 0;
   out_9063386925137587863[74] = 0;
   out_9063386925137587863[75] = 0;
   out_9063386925137587863[76] = 0;
   out_9063386925137587863[77] = 0;
   out_9063386925137587863[78] = 0;
   out_9063386925137587863[79] = 0;
   out_9063386925137587863[80] = 1.0;
}
void f_fun(double *state, double dt, double *out_4367013321197196315) {
   out_4367013321197196315[0] = state[0];
   out_4367013321197196315[1] = state[1];
   out_4367013321197196315[2] = state[2];
   out_4367013321197196315[3] = state[3];
   out_4367013321197196315[4] = state[4];
   out_4367013321197196315[5] = dt*((-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]))*state[6] - 9.8000000000000007*state[8] + stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*state[1]) + (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*state[4])) + state[5];
   out_4367013321197196315[6] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*state[4])) + state[6];
   out_4367013321197196315[7] = state[7];
   out_4367013321197196315[8] = state[8];
}
void F_fun(double *state, double dt, double *out_877178618622646886) {
   out_877178618622646886[0] = 1;
   out_877178618622646886[1] = 0;
   out_877178618622646886[2] = 0;
   out_877178618622646886[3] = 0;
   out_877178618622646886[4] = 0;
   out_877178618622646886[5] = 0;
   out_877178618622646886[6] = 0;
   out_877178618622646886[7] = 0;
   out_877178618622646886[8] = 0;
   out_877178618622646886[9] = 0;
   out_877178618622646886[10] = 1;
   out_877178618622646886[11] = 0;
   out_877178618622646886[12] = 0;
   out_877178618622646886[13] = 0;
   out_877178618622646886[14] = 0;
   out_877178618622646886[15] = 0;
   out_877178618622646886[16] = 0;
   out_877178618622646886[17] = 0;
   out_877178618622646886[18] = 0;
   out_877178618622646886[19] = 0;
   out_877178618622646886[20] = 1;
   out_877178618622646886[21] = 0;
   out_877178618622646886[22] = 0;
   out_877178618622646886[23] = 0;
   out_877178618622646886[24] = 0;
   out_877178618622646886[25] = 0;
   out_877178618622646886[26] = 0;
   out_877178618622646886[27] = 0;
   out_877178618622646886[28] = 0;
   out_877178618622646886[29] = 0;
   out_877178618622646886[30] = 1;
   out_877178618622646886[31] = 0;
   out_877178618622646886[32] = 0;
   out_877178618622646886[33] = 0;
   out_877178618622646886[34] = 0;
   out_877178618622646886[35] = 0;
   out_877178618622646886[36] = 0;
   out_877178618622646886[37] = 0;
   out_877178618622646886[38] = 0;
   out_877178618622646886[39] = 0;
   out_877178618622646886[40] = 1;
   out_877178618622646886[41] = 0;
   out_877178618622646886[42] = 0;
   out_877178618622646886[43] = 0;
   out_877178618622646886[44] = 0;
   out_877178618622646886[45] = dt*(stiffness_front*(-state[2] - state[3] + state[7])/(mass*state[1]) + (-stiffness_front - stiffness_rear)*state[5]/(mass*state[4]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[6]/(mass*state[4]));
   out_877178618622646886[46] = -dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*pow(state[1], 2));
   out_877178618622646886[47] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_877178618622646886[48] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_877178618622646886[49] = dt*((-1 - (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*pow(state[4], 2)))*state[6] - (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*pow(state[4], 2)));
   out_877178618622646886[50] = dt*(-stiffness_front*state[0] - stiffness_rear*state[0])/(mass*state[4]) + 1;
   out_877178618622646886[51] = dt*(-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]));
   out_877178618622646886[52] = dt*stiffness_front*state[0]/(mass*state[1]);
   out_877178618622646886[53] = -9.8000000000000007*dt;
   out_877178618622646886[54] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front - pow(center_to_rear, 2)*stiffness_rear)*state[6]/(rotational_inertia*state[4]));
   out_877178618622646886[55] = -center_to_front*dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*pow(state[1], 2));
   out_877178618622646886[56] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_877178618622646886[57] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_877178618622646886[58] = dt*(-(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*pow(state[4], 2)) - (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*pow(state[4], 2)));
   out_877178618622646886[59] = dt*(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(rotational_inertia*state[4]);
   out_877178618622646886[60] = dt*(-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])/(rotational_inertia*state[4]) + 1;
   out_877178618622646886[61] = center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_877178618622646886[62] = 0;
   out_877178618622646886[63] = 0;
   out_877178618622646886[64] = 0;
   out_877178618622646886[65] = 0;
   out_877178618622646886[66] = 0;
   out_877178618622646886[67] = 0;
   out_877178618622646886[68] = 0;
   out_877178618622646886[69] = 0;
   out_877178618622646886[70] = 1;
   out_877178618622646886[71] = 0;
   out_877178618622646886[72] = 0;
   out_877178618622646886[73] = 0;
   out_877178618622646886[74] = 0;
   out_877178618622646886[75] = 0;
   out_877178618622646886[76] = 0;
   out_877178618622646886[77] = 0;
   out_877178618622646886[78] = 0;
   out_877178618622646886[79] = 0;
   out_877178618622646886[80] = 1;
}
void h_25(double *state, double *unused, double *out_5316720470994993207) {
   out_5316720470994993207[0] = state[6];
}
void H_25(double *state, double *unused, double *out_5862606352711225515) {
   out_5862606352711225515[0] = 0;
   out_5862606352711225515[1] = 0;
   out_5862606352711225515[2] = 0;
   out_5862606352711225515[3] = 0;
   out_5862606352711225515[4] = 0;
   out_5862606352711225515[5] = 0;
   out_5862606352711225515[6] = 1;
   out_5862606352711225515[7] = 0;
   out_5862606352711225515[8] = 0;
}
void h_24(double *state, double *unused, double *out_2076230150111509254) {
   out_2076230150111509254[0] = state[4];
   out_2076230150111509254[1] = state[5];
}
void H_24(double *state, double *unused, double *out_3689956753705725949) {
   out_3689956753705725949[0] = 0;
   out_3689956753705725949[1] = 0;
   out_3689956753705725949[2] = 0;
   out_3689956753705725949[3] = 0;
   out_3689956753705725949[4] = 1;
   out_3689956753705725949[5] = 0;
   out_3689956753705725949[6] = 0;
   out_3689956753705725949[7] = 0;
   out_3689956753705725949[8] = 0;
   out_3689956753705725949[9] = 0;
   out_3689956753705725949[10] = 0;
   out_3689956753705725949[11] = 0;
   out_3689956753705725949[12] = 0;
   out_3689956753705725949[13] = 0;
   out_3689956753705725949[14] = 1;
   out_3689956753705725949[15] = 0;
   out_3689956753705725949[16] = 0;
   out_3689956753705725949[17] = 0;
}
void h_30(double *state, double *unused, double *out_9178403947423494859) {
   out_9178403947423494859[0] = state[4];
}
void H_30(double *state, double *unused, double *out_1334910022583617317) {
   out_1334910022583617317[0] = 0;
   out_1334910022583617317[1] = 0;
   out_1334910022583617317[2] = 0;
   out_1334910022583617317[3] = 0;
   out_1334910022583617317[4] = 1;
   out_1334910022583617317[5] = 0;
   out_1334910022583617317[6] = 0;
   out_1334910022583617317[7] = 0;
   out_1334910022583617317[8] = 0;
}
void h_26(double *state, double *unused, double *out_590241265618653451) {
   out_590241265618653451[0] = state[7];
}
void H_26(double *state, double *unused, double *out_2121103033837169291) {
   out_2121103033837169291[0] = 0;
   out_2121103033837169291[1] = 0;
   out_2121103033837169291[2] = 0;
   out_2121103033837169291[3] = 0;
   out_2121103033837169291[4] = 0;
   out_2121103033837169291[5] = 0;
   out_2121103033837169291[6] = 0;
   out_2121103033837169291[7] = 1;
   out_2121103033837169291[8] = 0;
}
void h_27(double *state, double *unused, double *out_3626272636259312247) {
   out_3626272636259312247[0] = state[3];
}
void H_27(double *state, double *unused, double *out_839853289216807594) {
   out_839853289216807594[0] = 0;
   out_839853289216807594[1] = 0;
   out_839853289216807594[2] = 0;
   out_839853289216807594[3] = 1;
   out_839853289216807594[4] = 0;
   out_839853289216807594[5] = 0;
   out_839853289216807594[6] = 0;
   out_839853289216807594[7] = 0;
   out_839853289216807594[8] = 0;
}
void h_29(double *state, double *unused, double *out_4266666858625211112) {
   out_4266666858625211112[0] = state[1];
}
void H_29(double *state, double *unused, double *out_1845141366898009501) {
   out_1845141366898009501[0] = 0;
   out_1845141366898009501[1] = 1;
   out_1845141366898009501[2] = 0;
   out_1845141366898009501[3] = 0;
   out_1845141366898009501[4] = 0;
   out_1845141366898009501[5] = 0;
   out_1845141366898009501[6] = 0;
   out_1845141366898009501[7] = 0;
   out_1845141366898009501[8] = 0;
}
void h_28(double *state, double *unused, double *out_1336424566648998087) {
   out_1336424566648998087[0] = state[0];
}
void H_28(double *state, double *unused, double *out_3808771638463335752) {
   out_3808771638463335752[0] = 1;
   out_3808771638463335752[1] = 0;
   out_3808771638463335752[2] = 0;
   out_3808771638463335752[3] = 0;
   out_3808771638463335752[4] = 0;
   out_3808771638463335752[5] = 0;
   out_3808771638463335752[6] = 0;
   out_3808771638463335752[7] = 0;
   out_3808771638463335752[8] = 0;
}
void h_31(double *state, double *unused, double *out_8652952095776365950) {
   out_8652952095776365950[0] = state[8];
}
void H_31(double *state, double *unused, double *out_1494894931603817815) {
   out_1494894931603817815[0] = 0;
   out_1494894931603817815[1] = 0;
   out_1494894931603817815[2] = 0;
   out_1494894931603817815[3] = 0;
   out_1494894931603817815[4] = 0;
   out_1494894931603817815[5] = 0;
   out_1494894931603817815[6] = 0;
   out_1494894931603817815[7] = 0;
   out_1494894931603817815[8] = 1;
}
#include <eigen3/Eigen/Dense>
#include <iostream>

typedef Eigen::Matrix<double, DIM, DIM, Eigen::RowMajor> DDM;
typedef Eigen::Matrix<double, EDIM, EDIM, Eigen::RowMajor> EEM;
typedef Eigen::Matrix<double, DIM, EDIM, Eigen::RowMajor> DEM;

void predict(double *in_x, double *in_P, double *in_Q, double dt) {
  typedef Eigen::Matrix<double, MEDIM, MEDIM, Eigen::RowMajor> RRM;

  double nx[DIM] = {0};
  double in_F[EDIM*EDIM] = {0};

  // functions from sympy
  f_fun(in_x, dt, nx);
  F_fun(in_x, dt, in_F);


  EEM F(in_F);
  EEM P(in_P);
  EEM Q(in_Q);

  RRM F_main = F.topLeftCorner(MEDIM, MEDIM);
  P.topLeftCorner(MEDIM, MEDIM) = (F_main * P.topLeftCorner(MEDIM, MEDIM)) * F_main.transpose();
  P.topRightCorner(MEDIM, EDIM - MEDIM) = F_main * P.topRightCorner(MEDIM, EDIM - MEDIM);
  P.bottomLeftCorner(EDIM - MEDIM, MEDIM) = P.bottomLeftCorner(EDIM - MEDIM, MEDIM) * F_main.transpose();

  P = P + dt*Q;

  // copy out state
  memcpy(in_x, nx, DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
}

// note: extra_args dim only correct when null space projecting
// otherwise 1
template <int ZDIM, int EADIM, bool MAHA_TEST>
void update(double *in_x, double *in_P, Hfun h_fun, Hfun H_fun, Hfun Hea_fun, double *in_z, double *in_R, double *in_ea, double MAHA_THRESHOLD) {
  typedef Eigen::Matrix<double, ZDIM, ZDIM, Eigen::RowMajor> ZZM;
  typedef Eigen::Matrix<double, ZDIM, DIM, Eigen::RowMajor> ZDM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, EDIM, Eigen::RowMajor> XEM;
  //typedef Eigen::Matrix<double, EDIM, ZDIM, Eigen::RowMajor> EZM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, 1> X1M;
  typedef Eigen::Matrix<double, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor> XXM;

  double in_hx[ZDIM] = {0};
  double in_H[ZDIM * DIM] = {0};
  double in_H_mod[EDIM * DIM] = {0};
  double delta_x[EDIM] = {0};
  double x_new[DIM] = {0};


  // state x, P
  Eigen::Matrix<double, ZDIM, 1> z(in_z);
  EEM P(in_P);
  ZZM pre_R(in_R);

  // functions from sympy
  h_fun(in_x, in_ea, in_hx);
  H_fun(in_x, in_ea, in_H);
  ZDM pre_H(in_H);

  // get y (y = z - hx)
  Eigen::Matrix<double, ZDIM, 1> pre_y(in_hx); pre_y = z - pre_y;
  X1M y; XXM H; XXM R;
  if (Hea_fun){
    typedef Eigen::Matrix<double, ZDIM, EADIM, Eigen::RowMajor> ZAM;
    double in_Hea[ZDIM * EADIM] = {0};
    Hea_fun(in_x, in_ea, in_Hea);
    ZAM Hea(in_Hea);
    XXM A = Hea.transpose().fullPivLu().kernel();


    y = A.transpose() * pre_y;
    H = A.transpose() * pre_H;
    R = A.transpose() * pre_R * A;
  } else {
    y = pre_y;
    H = pre_H;
    R = pre_R;
  }
  // get modified H
  H_mod_fun(in_x, in_H_mod);
  DEM H_mod(in_H_mod);
  XEM H_err = H * H_mod;

  // Do mahalobis distance test
  if (MAHA_TEST){
    XXM a = (H_err * P * H_err.transpose() + R).inverse();
    double maha_dist = y.transpose() * a * y;
    if (maha_dist > MAHA_THRESHOLD){
      R = 1.0e16 * R;
    }
  }

  // Outlier resilient weighting
  double weight = 1;//(1.5)/(1 + y.squaredNorm()/R.sum());

  // kalman gains and I_KH
  XXM S = ((H_err * P) * H_err.transpose()) + R/weight;
  XEM KT = S.fullPivLu().solve(H_err * P.transpose());
  //EZM K = KT.transpose(); TODO: WHY DOES THIS NOT COMPILE?
  //EZM K = S.fullPivLu().solve(H_err * P.transpose()).transpose();
  //std::cout << "Here is the matrix rot:\n" << K << std::endl;
  EEM I_KH = Eigen::Matrix<double, EDIM, EDIM>::Identity() - (KT.transpose() * H_err);

  // update state by injecting dx
  Eigen::Matrix<double, EDIM, 1> dx(delta_x);
  dx  = (KT.transpose() * y);
  memcpy(delta_x, dx.data(), EDIM * sizeof(double));
  err_fun(in_x, delta_x, x_new);
  Eigen::Matrix<double, DIM, 1> x(x_new);

  // update cov
  P = ((I_KH * P) * I_KH.transpose()) + ((KT.transpose() * R) * KT);

  // copy out state
  memcpy(in_x, x.data(), DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
  memcpy(in_z, y.data(), y.rows() * sizeof(double));
}




}
extern "C" {

void car_update_25(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_25, H_25, NULL, in_z, in_R, in_ea, MAHA_THRESH_25);
}
void car_update_24(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<2, 3, 0>(in_x, in_P, h_24, H_24, NULL, in_z, in_R, in_ea, MAHA_THRESH_24);
}
void car_update_30(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_30, H_30, NULL, in_z, in_R, in_ea, MAHA_THRESH_30);
}
void car_update_26(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_26, H_26, NULL, in_z, in_R, in_ea, MAHA_THRESH_26);
}
void car_update_27(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_27, H_27, NULL, in_z, in_R, in_ea, MAHA_THRESH_27);
}
void car_update_29(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_29, H_29, NULL, in_z, in_R, in_ea, MAHA_THRESH_29);
}
void car_update_28(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_28, H_28, NULL, in_z, in_R, in_ea, MAHA_THRESH_28);
}
void car_update_31(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_31, H_31, NULL, in_z, in_R, in_ea, MAHA_THRESH_31);
}
void car_err_fun(double *nom_x, double *delta_x, double *out_300495555088403105) {
  err_fun(nom_x, delta_x, out_300495555088403105);
}
void car_inv_err_fun(double *nom_x, double *true_x, double *out_606621225230243076) {
  inv_err_fun(nom_x, true_x, out_606621225230243076);
}
void car_H_mod_fun(double *state, double *out_9063386925137587863) {
  H_mod_fun(state, out_9063386925137587863);
}
void car_f_fun(double *state, double dt, double *out_4367013321197196315) {
  f_fun(state,  dt, out_4367013321197196315);
}
void car_F_fun(double *state, double dt, double *out_877178618622646886) {
  F_fun(state,  dt, out_877178618622646886);
}
void car_h_25(double *state, double *unused, double *out_5316720470994993207) {
  h_25(state, unused, out_5316720470994993207);
}
void car_H_25(double *state, double *unused, double *out_5862606352711225515) {
  H_25(state, unused, out_5862606352711225515);
}
void car_h_24(double *state, double *unused, double *out_2076230150111509254) {
  h_24(state, unused, out_2076230150111509254);
}
void car_H_24(double *state, double *unused, double *out_3689956753705725949) {
  H_24(state, unused, out_3689956753705725949);
}
void car_h_30(double *state, double *unused, double *out_9178403947423494859) {
  h_30(state, unused, out_9178403947423494859);
}
void car_H_30(double *state, double *unused, double *out_1334910022583617317) {
  H_30(state, unused, out_1334910022583617317);
}
void car_h_26(double *state, double *unused, double *out_590241265618653451) {
  h_26(state, unused, out_590241265618653451);
}
void car_H_26(double *state, double *unused, double *out_2121103033837169291) {
  H_26(state, unused, out_2121103033837169291);
}
void car_h_27(double *state, double *unused, double *out_3626272636259312247) {
  h_27(state, unused, out_3626272636259312247);
}
void car_H_27(double *state, double *unused, double *out_839853289216807594) {
  H_27(state, unused, out_839853289216807594);
}
void car_h_29(double *state, double *unused, double *out_4266666858625211112) {
  h_29(state, unused, out_4266666858625211112);
}
void car_H_29(double *state, double *unused, double *out_1845141366898009501) {
  H_29(state, unused, out_1845141366898009501);
}
void car_h_28(double *state, double *unused, double *out_1336424566648998087) {
  h_28(state, unused, out_1336424566648998087);
}
void car_H_28(double *state, double *unused, double *out_3808771638463335752) {
  H_28(state, unused, out_3808771638463335752);
}
void car_h_31(double *state, double *unused, double *out_8652952095776365950) {
  h_31(state, unused, out_8652952095776365950);
}
void car_H_31(double *state, double *unused, double *out_1494894931603817815) {
  H_31(state, unused, out_1494894931603817815);
}
void car_predict(double *in_x, double *in_P, double *in_Q, double dt) {
  predict(in_x, in_P, in_Q, dt);
}
void car_set_mass(double x) {
  set_mass(x);
}
void car_set_rotational_inertia(double x) {
  set_rotational_inertia(x);
}
void car_set_center_to_front(double x) {
  set_center_to_front(x);
}
void car_set_center_to_rear(double x) {
  set_center_to_rear(x);
}
void car_set_stiffness_front(double x) {
  set_stiffness_front(x);
}
void car_set_stiffness_rear(double x) {
  set_stiffness_rear(x);
}
}

const EKF car = {
  .name = "car",
  .kinds = { 25, 24, 30, 26, 27, 29, 28, 31 },
  .feature_kinds = {  },
  .f_fun = car_f_fun,
  .F_fun = car_F_fun,
  .err_fun = car_err_fun,
  .inv_err_fun = car_inv_err_fun,
  .H_mod_fun = car_H_mod_fun,
  .predict = car_predict,
  .hs = {
    { 25, car_h_25 },
    { 24, car_h_24 },
    { 30, car_h_30 },
    { 26, car_h_26 },
    { 27, car_h_27 },
    { 29, car_h_29 },
    { 28, car_h_28 },
    { 31, car_h_31 },
  },
  .Hs = {
    { 25, car_H_25 },
    { 24, car_H_24 },
    { 30, car_H_30 },
    { 26, car_H_26 },
    { 27, car_H_27 },
    { 29, car_H_29 },
    { 28, car_H_28 },
    { 31, car_H_31 },
  },
  .updates = {
    { 25, car_update_25 },
    { 24, car_update_24 },
    { 30, car_update_30 },
    { 26, car_update_26 },
    { 27, car_update_27 },
    { 29, car_update_29 },
    { 28, car_update_28 },
    { 31, car_update_31 },
  },
  .Hes = {
  },
  .sets = {
    { "mass", car_set_mass },
    { "rotational_inertia", car_set_rotational_inertia },
    { "center_to_front", car_set_center_to_front },
    { "center_to_rear", car_set_center_to_rear },
    { "stiffness_front", car_set_stiffness_front },
    { "stiffness_rear", car_set_stiffness_rear },
  },
  .extra_routines = {
  },
};

ekf_lib_init(car)
